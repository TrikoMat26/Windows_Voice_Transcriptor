# -*- coding: utf-8 -*-
"""
Application de transcription vocale pour Windows.
Utilise PySide6 pour l'interface, sounddevice pour l'enregistrement,
OpenAI pour la transcription, et pynput pour un raccourci clavier global (F9).
"""
import sys
import os
import tempfile
import time
import datetime
import threading
import webbrowser
import platform
from pathlib import Path  # CORRECTION: Ajout de l'import manquant

import numpy as np
import openai
import pyperclip
import sounddevice as sd
import soundfile as sf
from pynput import keyboard

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel, QMessageBox,
    QHBoxLayout, QProgressBar, QSizePolicy, QSystemTrayIcon, QMenu
)
from PySide6.QtGui import QFont, QIcon, QAction
from PySide6.QtCore import (
    QTimer, Qt, Signal, Slot, QObject, QThread,
    QSharedMemory, QSystemSemaphore
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket


# --- Configuration Globale ---
ICON_PATH = os.path.join(os.path.dirname(__file__), "mic.png")
SINGLE_INSTANCE_KEY = "VoiceTranscriptorAppUniqueKey"

# --- Gestion de l'Instance Unique ---
shared_memory = None
local_server = None

def is_already_running():
    global shared_memory
    semaphore = QSystemSemaphore(SINGLE_INSTANCE_KEY + "_sem", 1)
    semaphore.acquire()
    temp_shared = QSharedMemory(SINGLE_INSTANCE_KEY)
    if temp_shared.attach():
        temp_shared.detach()
    shared_memory = QSharedMemory(SINGLE_INSTANCE_KEY)
    already_running = not shared_memory.create(1)
    semaphore.release()
    return already_running

def send_show_request():
    socket = QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_KEY)
    if socket.waitForConnected(500):
        socket.write(b"show")
        socket.flush()
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()

def start_local_server(main_window):
    global local_server
    local_server = QLocalServer()
    try:
        QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
    except Exception:
        pass
    local_server.listen(SINGLE_INSTANCE_KEY)
    local_server.newConnection.connect(lambda: handle_new_connection(main_window))

def handle_new_connection(main_window):
    socket = local_server.nextPendingConnection()
    if socket and socket.waitForReadyRead(500):
        data = socket.readAll().data()
        if data == b"show":
            main_window.show_normal_window()
    socket.disconnectFromServer()


# --- Écouteur de Raccourci Clavier Global ---
class HotkeyListener(QObject):
    """
    Écoute un raccourci clavier global dans un thread séparé
    et émet un signal sécurisé pour le thread GUI.
    """
    hotkey_pressed = Signal()

    def __init__(self, hotkey):
        super().__init__()
        self.hotkey = keyboard.HotKey(hotkey, self.on_activate)
        self.listener = None

    @Slot()
    def start_listening(self):
        self.listener = keyboard.Listener(
            on_press=self.for_canonical(self.hotkey.press),
            on_release=self.for_canonical(self.hotkey.release)
        )
        self.listener.start()

    def for_canonical(self, f):
        return lambda k: f(self.listener.canonical(k))

    def on_activate(self):
        self.hotkey_pressed.emit()

    def stop_listening(self):
        if self.listener:
            self.listener.stop()


# --- Classe Principale de l'Application ---
class AudioRecorder(QMainWindow):
    show_success_signal = Signal(str)
    show_error_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Enregistreur Vocal")
        self.setFixedSize(400, 250)
        self.setStyleSheet(self.get_platform_stylesheet())
        self.setWindowIcon(QIcon(ICON_PATH))

        # Config audio
        self.sample_rate = 44100
        self.channels = 1
        self.recording = False
        self.audio_frames = []
        self.start_time = 0

        self.setup_recordings_dir()
        self.current_recording_path = None

        self.setup_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)

        self.check_openai_api_key()

        self.setup_systray()
        self.setup_global_hotkey()

        self.show_success_signal.connect(self.show_success)
        self.show_error_signal.connect(self.show_error)

        self.force_quit = False

    def check_openai_api_key(self):
        openai.api_key = os.getenv("OPENAI_API_KEY")
        if not openai.api_key:
            QMessageBox.critical(
                self, "Erreur de Configuration",
                "La clé API OpenAI n'a pas été trouvée.\n"
                "Veuillez définir la variable d'environnement OPENAI_API_KEY."
            )
            sys.exit(1)

    def setup_global_hotkey(self):
        self.hotkey_thread = QThread(self)
        self.hotkey_listener = HotkeyListener({keyboard.Key.f9})
        self.hotkey_listener.moveToThread(self.hotkey_thread)

        self.hotkey_thread.started.connect(self.hotkey_listener.start_listening)
        self.hotkey_listener.hotkey_pressed.connect(self.toggle_recording)

        self.hotkey_thread.start()

    def setup_systray(self):
        self.tray_icon = QSystemTrayIcon(QIcon(ICON_PATH), self)
        self.tray_icon.setToolTip("Enregistreur Vocal (F9 pour démarrer/arrêter)")
        
        tray_menu = QMenu(self)
        show_action = QAction("Afficher la fenêtre", self)
        show_action.triggered.connect(self.show_normal_window)
        
        quit_action = QAction("Quitter", self)
        quit_action.triggered.connect(self.quit_app)
        
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.handle_systray_activation)

    @Slot()
    def show_normal_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        # Astuce Windows pour forcer la fenêtre au premier plan
        if platform.system() == "Windows":
            import ctypes
            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)
            ctypes.windll.user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002)
            ctypes.windll.user32.SetForegroundWindow(hwnd)

    @Slot()
    def quit_app(self):
        self.force_quit = True
        self.close()

    def handle_systray_activation(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_normal_window()

    def get_platform_stylesheet(self):
        return """ QMainWindow{background-color:#f5f5f5}QLabel{color:#333}#filePathLabel{font-size:10px;color:#666;background-color:#f0f0f0;padding:4px;border-radius:3px;margin-top:10px}QLabel,QPushButton{font-family:'Segoe UI',Arial,sans-serif}QProgressBar{border:none;background:#e0e0e0;border-radius:2px}QProgressBar::chunk{background-color:#4CAF50;border-radius:2px} """

    def setup_recordings_dir(self):
        if platform.system() == "Windows":
            self.recordings_dir = Path.home() / "Documents" / "VoiceRecordings"
        else:
            self.recordings_dir = Path.home() / "VoiceRecordings"
        self.recordings_dir.mkdir(exist_ok=True, parents=True)

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        self.main_layout = QVBoxLayout(main_widget)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        # Conteneur principal
        self.content_widget = QWidget()
        layout = QVBoxLayout(self.content_widget)
        layout.setSpacing(15)
        
        self.time_label = QLabel("00:00")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        
        self.transcribe_btn = QPushButton("Démarrer (F9)")
        self.transcribe_btn.setStyleSheet("QPushButton{background-color:#4CAF50;color:white;padding:8px 16px;border:none;border-radius:4px;font-weight:bold}QPushButton:disabled{background-color:#a5d6a7}")
        self.transcribe_btn.clicked.connect(self.toggle_recording)

        self.cancel_btn = QPushButton("Annuler")
        self.cancel_btn.setStyleSheet("QPushButton{background-color:#f44336;color:white;padding:8px 16px;border:none;border-radius:4px;font-weight:bold}QPushButton:disabled{background-color:#ef9a9a}")
        self.cancel_btn.clicked.connect(self.cancel_recording)
        self.cancel_btn.setEnabled(False)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.transcribe_btn)
        button_layout.addWidget(self.cancel_btn)

        self.file_path_label = QLabel()
        self.file_path_label.setObjectName("filePathLabel")
        self.file_path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_path_label.setWordWrap(True)

        layout.addWidget(self.time_label)
        layout.addLayout(button_layout)
        layout.addWidget(self.file_path_label)
        
        self.main_layout.addWidget(self.content_widget)

        # Conteneur de chargement
        self.loading_widget = QWidget()
        loading_layout = QVBoxLayout(self.loading_widget)
        self.loading_label = QLabel()
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("font-size: 14px; color: #555;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        loading_layout.addWidget(self.loading_label)
        loading_layout.addWidget(self.progress_bar)
        self.main_layout.addWidget(self.loading_widget)
        self.loading_widget.hide()

    @Slot()
    def toggle_recording(self):
        if not self.recording:
            self.show_normal_window()
            QApplication.processEvents()
            self.start_recording()
        else:
            self.finish_recording()

    def start_recording(self):
        self.recording = True
        self.audio_frames = []
        self.start_time = time.time()
        self.timer.start(100)
        
        self.transcribe_btn.setText("Terminer (F9)")
        self.cancel_btn.setEnabled(True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_recording_path = self.recordings_dir / f"recording_{timestamp}.wav"
        self.file_path_label.setText(f"Enregistrement en cours...")

        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate, channels=self.channels,
                callback=self.audio_callback, dtype='float32'
            )
            self.stream.start()
        except Exception as e:
            self.show_error(f"Erreur de micro: {e}")
            self.reset_ui_for_next_transcription()

    def audio_callback(self, indata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        if self.recording:
            self.audio_frames.append(indata.copy())

    def update_timer(self):
        if self.recording:
            elapsed = int(time.time() - self.start_time)
            self.time_label.setText(f"{elapsed // 60:02d}:{elapsed % 60:02d}")

    def finish_recording(self):
        if not self.recording: return
        self.stop_recording_internals()
        
        self.transcribe_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.show_loading("Transcription en cours...")
        
        if not self.audio_frames:
            self.show_error("Aucun audio enregistré.")
            return

        audio_data = np.concatenate(self.audio_frames, axis=0)
        
        threading.Thread(target=self.process_audio_thread, args=(audio_data,), daemon=True).start()

    def process_audio_thread(self, audio_data):
        tmp_path = None
        try:
            # Sauvegarde en mémoire temporaire
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                sf.write(tmp_file.name, audio_data, self.sample_rate)
                tmp_path = tmp_file.name

            # Sauvegarde permanente
            sf.write(str(self.current_recording_path), audio_data, self.sample_rate)

            # Transcription
            with open(tmp_path, "rb") as audio_file:
                response = openai.audio.transcriptions.create(model="whisper-1", file=audio_file)
            
            os.unlink(tmp_path)
            
            pyperclip.copy(response.text)
            self.show_success_signal.emit("Transcription copiée !")

        except Exception as e:
            self.show_error_signal.emit(f"Erreur: {str(e)}")
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    @Slot()
    def cancel_recording(self):
        if self.recording:
            self.stop_recording_internals()
        self.reset_ui_for_next_transcription()

    def stop_recording_internals(self):
        if hasattr(self, 'stream') and self.stream.active:
            self.stream.stop()
            self.stream.close()
        self.recording = False
        self.timer.stop()

    def show_loading(self, message):
        self.content_widget.hide()
        self.loading_label.setText(message)
        self.progress_bar.show()
        self.loading_widget.show()

    @Slot(str)
    def show_success(self, message):
        self.loading_label.setText(message)
        self.loading_label.setStyleSheet("color: #4CAF50; font-size: 16px; font-weight: bold;")
        self.progress_bar.hide()
        QTimer.singleShot(1500, self.reset_ui_for_next_transcription)

    @Slot(str)
    def show_error(self, error_message):
        self.loading_widget.show()
        self.content_widget.hide()
        self.loading_label.setText(error_message)
        self.loading_label.setStyleSheet("color: #f44336; font-size: 14px; font-weight: normal; word-wrap: break-word;")
        self.progress_bar.hide()
        QTimer.singleShot(4000, self.reset_ui_for_next_transcription)

    def reset_ui_for_next_transcription(self):
        self.transcribe_btn.setText("Démarrer (F9)")
        self.transcribe_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.loading_widget.hide()
        self.content_widget.show()
        self.time_label.setText("00:00")
        self.file_path_label.setText("")
        self.hide_to_systray()

    def hide_to_systray(self):
        self.hide()

    def closeEvent(self, event):
        if self.force_quit:
            self.tray_icon.hide()
            self.hotkey_listener.stop_listening()
            self.hotkey_thread.quit()
            self.hotkey_thread.wait(500)
            event.accept()
        else:
            event.ignore()
            self.hide_to_systray()
            self.tray_icon.showMessage(
                "Toujours Actif",
                "L'application tourne en arrière-plan.",
                QSystemTrayIcon.Icon.Information,
                2000
            )


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if is_already_running():
        send_show_request()
        return

    recorder = AudioRecorder()
    start_local_server(recorder)
    
    # Démarrer minimisé dans la barre des tâches
    recorder.hide_to_systray()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()