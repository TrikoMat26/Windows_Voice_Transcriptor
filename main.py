import sys
import os
import tempfile
import time
import datetime
import sounddevice as sd
import soundfile as sf
import numpy as np
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel, QMessageBox,
    QHBoxLayout, QProgressBar, QSizePolicy, QSystemTrayIcon, QMenu
)
from PySide6.QtGui import QFont, QIcon, QAction, QKeySequence, QShortcut
from PySide6.QtCore import QTimer, Qt, Signal, Slot

import openai
import pyperclip
import platform

ICON_PATH = os.path.join(os.path.dirname(__file__), "mic.png")  # mets une icône dans ton dossier

class AudioRecorder(QMainWindow):
    show_success_signal = Signal(str)
    show_error_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Enregistreur Vocal")
        self.setFixedSize(400, 250)
        self.setStyleSheet(self.get_platform_stylesheet())

        # Audio config
        self.sample_rate = 44100
        self.channels = 1
        self.recording = False
        self.audio_frames = []
        self.start_time = 0

        # Dossier de sauvegarde des enregistrements
        self.setup_recordings_dir()
        self.current_recording_path = None

        # UI config
        self.setup_ui()

        # Timer pour le chrono
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_timer)

        # OpenAI config
        openai.api_key = os.getenv("OPENAI_API_KEY")
        if not openai.api_key:
            QMessageBox.critical(
                self,
                "Erreur",
                "La clé API OpenAI n'a pas été trouvée. Veuillez définir la variable d'environnement OPENAI_API_KEY."
            )
            sys.exit(1)

        # Systray
        self.setup_systray()

        self.show_success_signal.connect(self.show_success)
        self.show_error_signal.connect(self.show_error)

        # Raccourci clavier interne (F9)
        shortcut = QShortcut(QKeySequence("F9"), self)
        shortcut.activated.connect(self.toggle_recording)

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

    @Slot()
    def quit_app(self):
        self.tray_icon.hide()
        self.close()

    def handle_systray_activation(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.show_normal_window()

    def get_platform_stylesheet(self):
        base_style = """
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
        """
        if platform.system() == "Windows":
            return base_style + """
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
        return base_style

    def setup_recordings_dir(self):
        if platform.system() == "Windows":
            self.recordings_dir = Path.home() / "Documents" / "VoiceRecordings"
        else:
            self.recordings_dir = Path.home() / "VoiceRecordings"
        self.recordings_dir.mkdir(exist_ok=True, parents=True)

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)

        self.content_widget = QWidget()
        self.main_layout.addWidget(self.content_widget)

        layout = QVBoxLayout(self.content_widget)

        self.time_label = QLabel("00:00")
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setStyleSheet("font-size: 24px; font-weight: bold;")

        self.button_container = QWidget()
        button_layout = QHBoxLayout(self.button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(10)

        self.transcribe_btn = QPushButton("Démarrer la transcription")
        self.transcribe_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:disabled {
                background-color: #a5d6a7;
            }
        """)
        self.transcribe_btn.clicked.connect(self.toggle_recording)

        self.cancel_btn = QPushButton("Annuler")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:disabled {
                background-color: #ef9a9a;
            }
        """)
        self.cancel_btn.clicked.connect(self.cancel_recording)

        button_layout.addWidget(self.transcribe_btn)
        button_layout.addWidget(self.cancel_btn)

        self.file_path_label = QLabel()
        self.file_path_label.setObjectName("filePathLabel")
        self.file_path_label.setAlignment(Qt.AlignCenter)
        self.file_path_label.setWordWrap(True)
        self.file_path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout.addWidget(self.time_label, alignment=Qt.AlignCenter)
        layout.addWidget(self.button_container, alignment=Qt.AlignCenter)
        layout.addWidget(self.file_path_label, alignment=Qt.AlignCenter)

        self.loading_widget = QWidget()
        loading_layout = QVBoxLayout(self.loading_widget)
        loading_layout.setContentsMargins(0, 0, 0, 0)
        loading_layout.setSpacing(15)

        self.loading_label = QLabel()
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("font-size: 14px; color: #555;")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background: #e0e0e0;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 2px;
            }
        """)

        loading_layout.addWidget(self.loading_label, alignment=Qt.AlignCenter)
        loading_layout.addWidget(self.progress_bar)

        self.main_layout.addWidget(self.loading_widget)
        self.loading_widget.hide()

        main_widget.setLayout(self.main_layout)

    @Slot()
    def toggle_recording(self):
        if not self.recording:
            self.start_transcription_workflow()
        else:
            self.finish_recording()

    def start_transcription_workflow(self):
        self.transcribe_btn.setText("Terminer")
        self.transcribe_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        QApplication.processEvents()
        self.start_recording()

    def start_recording(self):
        self.recording = True
        self.audio_frames = []
        self.start_time = time.time()
        self.timer.start(100)
        self.update_timer()

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_recording_path = self.recordings_dir / f"recording_{timestamp}.wav"
        self.file_path_label.setText(f"Enregistrement en cours : {self.current_recording_path}")

        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            callback=self.audio_callback
        )
        self.stream.start()

    def audio_callback(self, indata, frames, time, status):
        if self.recording:
            self.audio_frames.append(indata.copy())

    def update_timer(self):
        if self.recording:
            elapsed = int(time.time() - self.start_time)
            minutes = elapsed // 60
            seconds = elapsed % 60
            self.time_label.setText(f"{minutes:02d}:{seconds:02d}")

    def show_loading(self, message):
        self.content_widget.hide()
        self.loading_label.setText(message)
        self.loading_label.setStyleSheet("font-size: 14px; color: #555;")
        self.progress_bar.show()
        self.loading_widget.show()

    @Slot(str)
    def show_success(self, message, close_delay=1500):
        self.loading_label.setText(message)
        self.loading_label.setStyleSheet("color: #4CAF50; font-size: 16px; font-weight: bold;")
        self.progress_bar.hide()
        QTimer.singleShot(close_delay, self.reset_ui_for_next_transcription)

    def reset_ui_for_next_transcription(self):
        self.transcribe_btn.setText("Démarrer la transcription")
        self.transcribe_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self.loading_widget.hide()
        self.content_widget.show()
        self.time_label.setText("00:00")
        self.file_path_label.setText("")
        self.recording = False
        self.hide_to_systray()

    def finish_recording(self):
        if not self.recording:
            return
        self.stop_recording()
        self.transcribe_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.show_loading("Transcription en cours...")

        def process_audio():
            tmp_file = None
            try:
                tmp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
                audio_data = np.concatenate(self.audio_frames, axis=0)
                sf.write(tmp_file.name, audio_data, self.sample_rate)
                if self.current_recording_path:
                    try:
                        sf.write(str(self.current_recording_path), audio_data, self.sample_rate)
                        self.file_path_label.setText(f"Enregistrement sauvegardé :\n{self.current_recording_path}")
                    except Exception:
                        self.file_path_label.setText(f"Erreur de sauvegarde, vérifiez les permissions :\n{self.recordings_dir}")
                with open(tmp_file.name, "rb") as audio_file:
                    response = openai.audio.transcriptions.create(
                        model="gpt-4o-transcribe",
                        file=audio_file
                    )
                transcription = response.text
                pyperclip.copy(transcription)
                success_msg = "Transcription terminée !"
                if self.current_recording_path:
                    success_msg += f"\nL'audio est sauvegardé ici :\n{self.current_recording_path}"
                self.show_success_signal.emit(success_msg)
            except Exception as e:
                error_msg = f"Erreur lors de la transcription : {str(e)}"
                if self.current_recording_path:
                    error_msg += f"\n\nL'enregistrement audio a été sauvegardé ici :\n{self.current_recording_path}"
                self.show_error_signal.emit(error_msg)
            finally:
                if tmp_file and os.path.exists(tmp_file.name):
                    for attempt in range(10):
                        try:
                            os.unlink(tmp_file.name)
                            break
                        except Exception:
                            time.sleep(0.2)
        import threading
        self.worker_thread = threading.Thread(target=process_audio, daemon=True)
        self.worker_thread.start()

    @Slot(str)
    def show_error(self, error_message):
        self.loading_label.setText(error_message)
        self.loading_label.setStyleSheet("color: #f44336; font-size: 16px; font-weight: bold;")
        self.progress_bar.hide()
        QTimer.singleShot(2000, self.reset_ui_for_next_transcription)

    def cancel_recording(self):
        if self.recording:
            self.stop_recording()
        self.reset_ui_for_next_transcription()  # Ajoute cette ligne pour réinitialiser l'UI
        self.hide_to_systray()

    def stop_recording(self):
        if hasattr(self, 'stream') and self.stream.active:
            self.stream.stop()
            self.stream.close()
        self.recording = False
        self.timer.stop()

    def hide_to_systray(self):
        self.hide()

    def closeEvent(self, event):
        event.ignore()
        self.hide_to_systray()
        self.tray_icon.showMessage(
            "Toujours actif",
            "L'application reste disponible dans la barre système.",
            QSystemTrayIcon.Information,
            2000
        )

def main():
    app = QApplication(sys.argv)
    recorder = AudioRecorder()
    recorder.hide_to_systray()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
