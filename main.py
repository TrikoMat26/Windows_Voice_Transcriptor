# -*- coding: utf-8 -*-
"""
Application de transcription vocale pour Windows.
Version Robuste avec séparation des threads pour le raccourci global.
"""
import sys
import os
import tempfile
import time
import datetime
import threading
import webbrowser
import platform
from pathlib import Path

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
    QTimer, Qt, Signal, Slot, QObject,
    QSharedMemory, QSystemSemaphore
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket

# --- Configuration Globale ---
# Icône par défaut si le fichier n'existe pas
ICON_PATH = os.path.join(os.path.dirname(__file__), "mic.png")
if not os.path.exists(ICON_PATH):
    ICON_PATH = None  # Utiliser l'icône par défaut du système

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

# --- NOUVELLE APPROCHE ROBUSTE POUR LE RACCOURCI ---
class SignalBus(QObject):
    """Un simple objet pour transporter nos signaux thread-safe."""
    hotkey_pressed = Signal()

def run_hotkey_listener(signal_bus, stop_event):
    """
    Cette fonction s'exécute dans un thread Python standard.
    Elle écoute le raccourci et émet un signal via le bus.
    """
    def on_activate():
        print("F9 détecté!")  # Debug
        signal_bus.hotkey_pressed.emit()

    try:
        hotkey = keyboard.HotKey(keyboard.HotKey.parse('<f9>'), on_activate)
        
        with keyboard.Listener(on_press=hotkey.press, on_release=hotkey.release) as listener:
            print("Écoute du raccourci F9 démarrée...")  # Debug
            while not stop_event.is_set():
                time.sleep(0.1)
            print("Arrêt de l'écoute du raccourci F9")  # Debug
            listener.stop()
    except Exception as e:
        print(f"Erreur dans l'écoute du raccourci: {e}")

# --- Classe Principale de l'Application ---
class AudioRecorder(QMainWindow):
    show_success_signal = Signal(str)
    show_error_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Enregistreur Vocal")
        self.setFixedSize(400, 280)
        self.setStyleSheet(self.get_platform_stylesheet())
        
        # Gestion de l'icône
        if ICON_PATH:
            self.setWindowIcon(QIcon(ICON_PATH))

        self.sample_rate = 44100
        self.channels = 1
        self.recording = False
        self.audio_frames = []
        self.start_time = 0

        self.setup_recordings_dir()
        self.setup_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)

        # Vérifier la clé API après l'initialisation de l'UI
        self.setup_systray()
        self.setup_global_hotkey()

        self.show_success_signal.connect(self.show_success)
        self.show_error_signal.connect(self.show_error)

        self.force_quit = False
        
        # Vérifier la clé API en dernier
        if not self.check_openai_api_key():
            self.show_api_key_warning()

    def check_openai_api_key(self):
        """Retourne True si la clé API est configurée, False sinon"""
        try:
            openai.api_key = os.getenv("OPENAI_API_KEY")
            if openai.api_key:
                print("Clé API OpenAI trouvée")
                return True
            else:
                print("Clé API OpenAI non trouvée")
                return False
        except Exception as e:
            print(f"Erreur lors de la vérification de la clé API: {e}")
            return False

    def show_api_key_warning(self):
        """Affiche un avertissement si la clé API n'est pas configurée"""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Clé API OpenAI manquante")
        msg.setText("La clé API OpenAI n'est pas configurée.")
        msg.setInformativeText(
            "L'application peut démarrer mais la transcription ne fonctionnera pas.\n\n"
            "Pour configurer votre clé API:\n"
            "1. Allez sur https://platform.openai.com/api-keys\n"
            "2. Créez une nouvelle clé API\n"
            "3. Définissez la variable d'environnement OPENAI_API_KEY"
        )
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Ignore)
        msg.setDefaultButton(QMessageBox.Ok)
        
        result = msg.exec()
        if result == QMessageBox.Ok:
            webbrowser.open("https://platform.openai.com/api-keys")

    def setup_global_hotkey(self):
        """Configuration du raccourci global F9"""
        try:
            self.signal_bus = SignalBus()
            self.signal_bus.hotkey_pressed.connect(self.toggle_recording)

            self.hotkey_stop_event = threading.Event()
            self.hotkey_thread = threading.Thread(
                target=run_hotkey_listener,
                args=(self.signal_bus, self.hotkey_stop_event),
                daemon=True
            )
            self.hotkey_thread.start()
            print("Thread de raccourci démarré")
        except Exception as e:
            print(f"Erreur lors de la configuration du raccourci: {e}")
            QMessageBox.warning(self, "Avertissement", 
                              f"Impossible de configurer le raccourci F9: {e}")
        
    def setup_systray(self):
        """Configuration de l'icône de la barre des tâches"""
        icon = QIcon(ICON_PATH) if ICON_PATH else self.style().standardIcon(self.style().SP_ComputerIcon)
        
        self.tray_icon = QSystemTrayIcon(icon, self)
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
        """Affiche la fenêtre principale"""
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if platform.system() == "Windows":
            try:
                import ctypes
                hwnd = int(self.winId())
                ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 3)
                ctypes.windll.user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 3)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception as e:
                print(f"Erreur lors de la mise au premier plan: {e}")

    @Slot()
    def quit_app(self):
        """Quitte l'application complètement"""
        self.force_quit = True
        self.close()

    def handle_systray_activation(self, reason):
        """Gère les clics sur l'icône de la barre des tâches"""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_normal_window()

    def get_platform_stylesheet(self):
        """Retourne le style CSS de l'application"""
        return """
        QMainWindow {
            background-color: #f5f5f5;
        }
        QLabel {
            color: #333;
        }
        #filePathLabel {
            font-size: 10px;
            color: #666;
            background-color: #f0f0f0;
            padding: 4px;
            border-radius: 3px;
            margin-top: 10px;
        }
        QLabel, QPushButton {
            font-family: 'Segoe UI', Arial, sans-serif;
        }
        QProgressBar {
            border: none;
            background: #e0e0e0;
            border-radius: 2px;
        }
        QProgressBar::chunk {
            background-color: #4CAF50;
            border-radius: 2px;
        }
        """

    def setup_recordings_dir(self):
        """Crée le dossier de sauvegarde des enregistrements"""
        if platform.system() == "Windows":
            self.recordings_dir = Path.home() / "Documents" / "VoiceRecordings"
        else:
            self.recordings_dir = Path.home() / "VoiceRecordings"
        
        try:
            self.recordings_dir.mkdir(exist_ok=True, parents=True)
            print(f"Dossier d'enregistrements: {self.recordings_dir}")
        except Exception as e:
            print(f"Erreur lors de la création du dossier: {e}")

    def setup_ui(self):
        """Configuration de l'interface utilisateur"""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        self.main_layout = QVBoxLayout(main_widget)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(10)

        self.content_widget = QWidget()
        layout = QVBoxLayout(self.content_widget)
        layout.setSpacing(10)
        
        self.time_label = QLabel("00:00")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        
        self.transcribe_btn = QPushButton("Démarrer (F9)")
        self.transcribe_btn.setStyleSheet(
            "QPushButton {"
            "background-color: #4CAF50;"
            "color: white;"
            "padding: 8px 16px;"
            "border: none;"
            "border-radius: 4px;"
            "font-weight: bold;"
            "}"
            "QPushButton:disabled {"
            "background-color: #a5d6a7;"
            "}"
        )
        self.transcribe_btn.clicked.connect(self.toggle_recording)

        self.cancel_btn = QPushButton("Annuler")
        self.cancel_btn.setStyleSheet(
            "QPushButton {"
            "background-color: #f44336;"
            "color: white;"
            "padding: 8px 16px;"
            "border: none;"
            "border-radius: 4px;"
            "font-weight: bold;"
            "}"
            "QPushButton:disabled {"
            "background-color: #ef9a9a;"
            "}"
        )
        self.cancel_btn.clicked.connect(self.cancel_recording)
        self.cancel_btn.setEnabled(False)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.transcribe_btn)
        button_layout.addWidget(self.cancel_btn)

        self.file_path_label = QLabel()
        self.file_path_label.setObjectName("filePathLabel")
        self.file_path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_path_label.setWordWrap(True)

        self.billing_btn = QPushButton("Voir mes crédits OpenAI")
        self.billing_btn.clicked.connect(
            lambda: webbrowser.open("https://platform.openai.com/account/billing/usage")
        )
        
        self.quit_btn = QPushButton("Quitter l'application")
        self.quit_btn.setStyleSheet(
            "QPushButton {"
            "background-color: #888;"
            "color: white;"
            "padding: 8px 16px;"
            "border: none;"
            "border-radius: 4px;"
            "}"
            "QPushButton:hover {"
            "background-color: #b71c1c;"
            "}"
        )
        self.quit_btn.clicked.connect(self.quit_app)
        
        layout.addWidget(self.time_label)
        layout.addLayout(button_layout)
        layout.addWidget(self.file_path_label)
        layout.addWidget(self.billing_btn)
        layout.addWidget(self.quit_btn)
        
        self.main_layout.addWidget(self.content_widget)

        # Widget de chargement
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
        """Démarre ou arrête l'enregistrement"""
        print(f"Toggle recording appelé, recording={self.recording}")
        if not self.recording:
            self.show_normal_window()
            self.start_recording()
        else:
            self.finish_recording()

    def start_recording(self):
        """Démarre l'enregistrement audio"""
        print("Démarrage de l'enregistrement...")
        self.recording = True
        self.audio_frames = []
        self.start_time = time.time()
        self.timer.start(100)
        self.transcribe_btn.setText("Terminer (F9)")
        self.cancel_btn.setEnabled(True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_recording_path = self.recordings_dir / f"recording_{timestamp}.wav"
        self.file_path_label.setText("Enregistrement en cours...")
        
        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate, 
                channels=self.channels, 
                callback=self.audio_callback, 
                dtype='float32'
            )
            self.stream.start()
            print("Stream audio démarré")
        except Exception as e:
            print(f"Erreur de micro: {e}")
            self.show_error(f"Erreur de micro: {e}")

    def audio_callback(self, indata, frames, time, status):
        """Callback pour capturer l'audio"""
        if status:
            print(f"Status audio: {status}", file=sys.stderr)
        if self.recording:
            self.audio_frames.append(indata.copy())

    def update_timer(self):
        """Met à jour l'affichage du timer"""
        if self.recording:
            elapsed = int(time.time() - self.start_time)
            self.time_label.setText(f"{elapsed // 60:02d}:{elapsed % 60:02d}")

    def finish_recording(self):
        """Termine l'enregistrement et lance la transcription"""
        if not self.recording:
            return
        
        print("Fin de l'enregistrement...")
        self.stop_recording_internals()
        self.transcribe_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        
        if not self.audio_frames:
            self.show_error("Aucun son n'a été enregistré.")
            return
        
        # Vérifier la clé API avant la transcription
        if not os.getenv("OPENAI_API_KEY"):
            self.show_error("Clé API OpenAI non configurée. Impossible de transcrire.")
            return
        
        self.show_loading("Transcription en cours...")
        audio_data = np.concatenate(self.audio_frames, axis=0)
        threading.Thread(target=self.process_audio_thread, args=(audio_data,), daemon=True).start()

    def process_audio_thread(self, audio_data):
        """Traite l'audio en arrière-plan"""
        tmp_path = None
        try:
            # Créer un fichier temporaire
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                sf.write(tmp_file.name, audio_data, self.sample_rate)
                tmp_path = tmp_file.name
            
            # Sauvegarder l'enregistrement
            sf.write(str(self.current_recording_path), audio_data, self.sample_rate)
            print(f"Enregistrement sauvegardé: {self.current_recording_path}")
            
            # Transcription avec OpenAI
            with open(tmp_path, "rb") as audio_file:
                response = openai.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
            
            # Nettoyer le fichier temporaire
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            
            # Copier le résultat dans le presse-papiers
            pyperclip.copy(response.text)
            print(f"Transcription: {response.text}")
            self.show_success_signal.emit("Transcription copiée dans le presse-papiers !")
            
        except Exception as e:
            print(f"Erreur de transcription: {e}")
            self.show_error_signal.emit(f"Erreur de transcription: {str(e)}")
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    @Slot()
    def cancel_recording(self):
        """Annule l'enregistrement en cours"""
        if self.recording:
            self.stop_recording_internals()
        self.reset_ui_for_next_transcription()

    def stop_recording_internals(self):
        """Arrête les composants internes d'enregistrement"""
        if hasattr(self, 'stream') and self.stream.active:
            self.stream.stop()
            self.stream.close()
        self.recording = False
        self.timer.stop()

    def show_loading(self, message):
        """Affiche l'écran de chargement"""
        self.content_widget.hide()
        self.loading_widget.show()
        self.loading_label.setText(message)
        self.progress_bar.show()

    @Slot(str)
    def show_success(self, message):
        """Affiche un message de succès"""
        self.loading_label.setText(message)
        self.loading_label.setStyleSheet("color: #4CAF50; font-size: 16px; font-weight: bold;")
        self.progress_bar.hide()
        QTimer.singleShot(1500, self.reset_ui_for_next_transcription)

    @Slot(str)
    def show_error(self, error_message):
        """Affiche un message d'erreur"""
        if not self.loading_widget.isVisible():
            self.content_widget.hide()
            self.loading_widget.show()
        
        self.loading_label.setText(error_message)
        self.loading_label.setStyleSheet("color: #f44336; font-size: 14px; font-weight: normal;")
        self.progress_bar.hide()
        QTimer.singleShot(4000, self.reset_ui_for_next_transcription)

    def reset_ui_for_next_transcription(self):
        """Remet l'interface à zéro pour la prochaine transcription"""
        self.transcribe_btn.setText("Démarrer (F9)")
        self.transcribe_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.loading_widget.hide()
        self.content_widget.show()
        self.time_label.setText("00:00")
        self.file_path_label.setText("")

    def hide_to_systray(self):
        """Cache l'application dans la barre des tâches"""
        self.hide()

    def closeEvent(self, event):
        """Gère la fermeture de l'application"""
        if self.force_quit:
            # Arrêter proprement le thread de raccourci
            if hasattr(self, 'hotkey_stop_event'):
                self.hotkey_stop_event.set()
            self.tray_icon.hide()
            event.accept()
        else:
            event.ignore()
            self.hide_to_systray()
            self.tray_icon.showMessage(
                "Toujours Actif", 
                "L'application tourne en arrière-plan. Utilisez F9 pour enregistrer.", 
                QSystemTrayIcon.Information, 
                2000
            )

def main():
    """Fonction principale"""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    # Vérifier si une instance est déjà en cours
    if is_already_running():
        print("Une instance est déjà en cours d'exécution")
        send_show_request()
        return
    
    print("Démarrage de l'application...")
    recorder = AudioRecorder()
    start_local_server(recorder)
    
    # Afficher la fenêtre au démarrage pour le debug
    recorder.show_normal_window()
    # Optionnel: masquer après quelques secondes
    # QTimer.singleShot(3000, recorder.hide_to_systray)
    
    print("Application démarrée, en attente...")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()