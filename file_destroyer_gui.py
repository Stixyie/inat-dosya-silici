#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Dosya ve Klasör Silme Aracı
Bu araç, kullanıcılara dosya ve klasörleri güvenli ve hızlı bir şekilde silme imkanı sağlar.
"""

import os as os
import stat as stat
import subprocess as subprocess
import shutil as shutil
import platform as platform
import time as time
import ctypes as ctypes
import sys as sys
import warnings as warnings
import traceback as traceback

# Daha spesifik uyarı bastırma
warnings.filterwarnings("ignore", category=DeprecationWarning, module="PyQt5.*", message="sipPyTypeDict()")
from ctypes import wintypes as wintypes
from PyQt5.QtWidgets import (QMainWindow, QApplication, QWidget, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QLabel, QProgressBar, 
                            QFileDialog, QTextEdit, QFrame, QStyleFactory, 
                            QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, 
                            QGraphicsOpacityEffect, QComboBox, QDialog, QGridLayout) 
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, 
    QPropertyAnimation, QEasingCurve, QPoint, 
    QSequentialAnimationGroup, QParallelAnimationGroup, 
    QRectF
) 
from PyQt5.QtGui import (
    QFont, QIcon, QPalette, QColor, 
    QPainter, QLinearGradient
) 

# Günlük ayarları
import logging as logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

try:
    import win32api as win32api
    import win32security as win32security
except ImportError:
    print("Pywin32 modülü bulunamadı. Lütfen 'pip install pywin32' ile yükleyin.")
    win32api = None
    win32security = None

# Windows API sabitleri
FILE_ALL_ACCESS = 0x1F01FF
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
GENERIC_ALL = 0x10000000
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
GENERIC_EXECUTE = 0x20000000

# Windows API fonksiyonları
kernel32 = ctypes.windll.kernel32
advapi32 = ctypes.windll.advapi32

class DeleteWorker(QThread):
    progress = pyqtSignal(dict)
    finished = pyqtSignal()
    log_message = pyqtSignal(str)  # Yeni sinyal için günlük kaydı
    confirmation_needed = pyqtSignal(str)  # Yeni sinyal için kullanıcı onayı
    result = pyqtSignal(dict)  # Yeni sinyal için sonuç

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.is_cancelled = False
        self.stats = {
            'total_files': 0,
            'deleted_files': 0,
            'failed_files': 0,
            'current_file': '',
            'elapsed_time': 0,
            'remaining_files': 0
        }
        self.start_time = time.time()
        self.cancelled_paths = set()

    def count_files(self, path):
        count = 0
        try:
            for root, dirs, files in os.walk(path):
                count += len(files) + len(dirs)
        except Exception as e:
            print(f"Error counting files: {e}")
        return count

    def is_system_path(self, path):
        """
        Sistemin kritik yollarını kontrol eder
        """
        system_paths = [
            'c:\\program files', 
            'c:\\windows', 
            'c:\\program files (x86)', 
            'c:\\users\\public',
            'c:\\users\\default'
        ]
        path_lower = path.lower()
        return any(path_lower.startswith(sys_path) for sys_path in system_paths)

    def take_ownership(self, path):
        """
        Dosya veya dizinin sahipliğini ele geçirmeye çalışır
        """
        try:
            # Sistem yolları için özel işlem
            if self.is_system_path(path):
                print(f"Sistem yolu, özel silme yöntemi gerekiyor: {path}")
                return False

            # Dosya/dizin için handle aç
            handle = kernel32.CreateFileW(
                path, 
                GENERIC_ALL, 
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, 
                None, 
                3,  # OPEN_EXISTING 
                0x02000000,  # FILE_FLAG_BACKUP_SEMANTICS (dizinler için gerekli)
                None
            )
            
            if handle == -1:
                print(f"Dosya/dizin açılamadı: {path}")
                return False
            
            kernel32.CloseHandle(handle)
            return True
        
        except Exception as e:
            print(f"Sahiplik alma hatası {path}: {e}")
            return False

    def force_delete_system_path(self, path):
        """
        Sistem yolları için zorlu silme mekanizması
        """
        try:
            # Komut satırı ile silme girişimleri
            commands = [
                f'takeown /f "{path}" /r /d y',
                f'icacls "{path}" /grant administrators:F /t',
                f'rd /s /q "{path}"' if os.path.isdir(path) else f'del /f /q "{path}"'
            ]
            
            for cmd in commands:
                try:
                    subprocess.run(cmd, shell=True, capture_output=True, text=True)
                except Exception as e:
                    print(f"Komut çalıştırma hatası: {cmd} - {e}")
            
            return not os.path.exists(path)
        
        except Exception as e:
            print(f"Sistem yolu silme hatası {path}: {e}")
            return False

    def safe_delete(self, path):
        try:
            # Dosya/dizin sahipliğini alma girişimi
            if not self.take_ownership(path):
                # Sahiplik alınamazsa sistem yolu silme mekanizması
                return self.force_delete_system_path(path)

            # Try multiple deletion strategies
            if os.path.isfile(path):
                # File-specific deletion
                try:
                    os.chmod(path, stat.S_IWRITE)  # Remove read-only attribute
                except:
                    pass
                
                try:
                    os.unlink(path)  # Direct file removal
                except PermissionError:
                    # Windows-specific handling
                    subprocess.run(['cmd', '/c', 'del', '/f', path], shell=True, capture_output=True)
            
            elif os.path.isdir(path):
                # Directory deletion with error handling
                try:
                    shutil.rmtree(path, ignore_errors=True)
                except:
                    subprocess.run(['cmd', '/c', 'rd', '/s', '/q', path], shell=True, capture_output=True)
            
            return not os.path.exists(path)
        
        except Exception as e:
            print(f"Deletion error for {path}: {e}")
            return False

    def assess_file_protection_level(self, path):
        """
        Dosyanın koruma seviyesini değerlendirir
        Tüm dosyaları silinebilir olarak işaretle
        
        Koruma seviyeleri:
        0 - Kullanıcı dosyası (silinebilir)
        2 - Kritik sistem dosyası (korumalı)
        """
        # Her dosyayı silinebilir olarak işaretle
        return 0

    def run(self):
        try:
            # Ensure paths is always a list
            paths = self.path if isinstance(self.path, list) else self.path.split(";")
            
            deleted_files = []
            failed_files = []
            
            # Toplam dosya sayısını hesapla
            total_files = len(paths)
            current_deleted = 0
            
            for path in paths:
                # İptal kontrolü
                if self.is_cancelled:
                    break
                
                # Path'i normalize et
                path = os.path.normpath(path)
                
                # Dosya/klasör mevcut değilse
                if not os.path.exists(path):
                    failed_files.append(path)
                    current_deleted += 1
                    self.progress.emit({
                        'total_files': total_files,
                        'deleted_files': current_deleted,
                        'failed_files': len(failed_files),
                        'current_file': path,
                        'remaining_files': total_files - current_deleted
                    })
                    continue
                
                try:
                    # Dosya veya dizin silme
                    if os.path.isdir(path):
                        # Klasör için tüm içeriği sil
                        for root, dirs, files in os.walk(path, topdown=False):
                            for name in files:
                                file_path = os.path.join(root, name)
                                try:
                                    os.chmod(file_path, 0o777)
                                    os.unlink(file_path)
                                    deleted_files.append(file_path)
                                except Exception:
                                    failed_files.append(file_path)
                            
                            for name in dirs:
                                dir_path = os.path.join(root, name)
                                try:
                                    os.chmod(dir_path, 0o777)
                                    os.rmdir(dir_path)
                                    deleted_files.append(dir_path)
                                except Exception:
                                    failed_files.append(dir_path)
                        
                        # Ana klasörü sil
                        try:
                            os.rmdir(path)
                            deleted_files.append(path)
                        except Exception:
                            failed_files.append(path)
                    else:
                        # Dosya silme
                        try:
                            os.chmod(path, 0o777)
                            os.unlink(path)
                            deleted_files.append(path)
                        except Exception:
                            failed_files.append(path)
                    
                    # Progress güncellemesi
                    current_deleted += 1
                    self.progress.emit({
                        'total_files': total_files,
                        'deleted_files': current_deleted,
                        'failed_files': len(failed_files),
                        'current_file': path,
                        'remaining_files': total_files - current_deleted
                    })
                
                except Exception:
                    failed_files.append(path)
            
            # Sonuç oluştur
            result = {
                'total_files': total_files,
                'deleted_files': len(deleted_files),
                'failed_files': len(failed_files),
                'deleted': deleted_files,
                'failed': failed_files
            }
            
            # Sonucu ve bitişi bildir
            self.result.emit(result)
            self.finished.emit()
        
        except Exception as e:
            # Hata durumunda sonucu bildir
            result = {
                'total_files': total_files if 'total_files' in locals() else 0,
                'deleted_files': 0,
                'failed_files': total_files if 'total_files' in locals() else 0,
                'deleted': [],
                'failed': paths if 'paths' in locals() else []
            }
            self.result.emit(result)
            self.finished.emit()

    def forceful_delete_paths(self, paths):
        """
        Verilen yolları zorla silme metodu
        
        Args:
            paths: Silinecek dosya/klasör yolları listesi
        """
        system_cleaner = SystemCleaner(logger=self.log_message.emit)
        
        for path in paths:
            try:
                if os.path.isdir(path):
                    # Klasör için tüm içeriği sil
                    for root, dirs, files in os.walk(path, topdown=False):
                        for name in files:
                            file_path = os.path.join(root, name)
                            system_cleaner.forceful_delete(file_path)
                        for name in dirs:
                            dir_path = os.path.join(root, name)
                            system_cleaner.forceful_delete(dir_path)
                    
                    # Son olarak ana klasörü sil
                    system_cleaner.forceful_delete(path)
                else:
                    # Dosya için doğrudan silme
                    system_cleaner.forceful_delete(path)
            except Exception as e:
                print(f"Zorla silme hatası: {path} - {e}")
                self.log_message.emit(f"Zorla silme hatası: {path} - {e}")
        
        # Geçici sürücüleri temizle
        system_cleaner.cleanup()

class SystemCleaner:
    def __init__(self, logger=None):
        """
        Sistem temizleme ve dosya silme için gelişmiş araç
        
        Args:
            logger: Günlük kayıt için optional logger nesnesi
        """
        self.logger = logger or print
        self.temp_driver_path = None

    def _elevate_privileges(self):
        """
        Yönetici ayrıcalıklarını kontrol et ve yükselt
        """
        try:
            if ctypes.windll.shell32.IsUserAnAdmin():
                return True
            
            # UAC ile yönetici izni iste
            ctypes.windll.shell32.ShellExecuteW(
                None, 
                "runas", 
                sys.executable, 
                " ".join(sys.argv), 
                None, 
                1
            )
            return False
        except Exception as e:
            print(f"Ayrıcalık yükseltme hatası: {e}")
            self.logger(f"Ayrıcalık yükseltme hatası: {e}")
            return False

    def stop_process_by_path(self, file_path):
        """
        Belirli bir dosya yolundaki tüm işlemleri durdur
        
        Args:
            file_path: Durdurulacak işlemin dosya yolu
        
        Returns:
            Durdurulan işlem sayısı
        """
        stopped_count = 0
        normalized_path = os.path.normpath(file_path).lower()
        
        for proc in psutil.process_iter(['exe']):
            try:
                if proc.exe().lower() == normalized_path:
                    print(f"Durdurulan işlem: {proc.name()} (PID: {proc.pid})")
                    self.logger(f"Durdurulan işlem: {proc.name()} (PID: {proc.pid})")
                    proc.terminate()
                    stopped_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        return stopped_count

    def stop_service_by_path(self, file_path):
        """
        Belirli bir dosya yolundaki servisleri durdur ve devre dışı bırak
        
        Args:
            file_path: Durdurulacak servisin dosya yolu
        
        Returns:
            Durdurulan servis sayısı
        """
        stopped_count = 0
        normalized_path = os.path.normpath(file_path).lower()
        
        for service in win32service.EnumServicesStatus(
            win32service.SC_MANAGER_ALL_ACCESS
        ):
            try:
                service_path = win32serviceutil.QueryServiceConfig(service[0]).lpBinaryPathName
                if normalized_path in service_path.lower():
                    try:
                        win32serviceutil.StopService(service[0])
                        win32serviceutil.ChangeServiceConfig(
                            service[0], 
                            win32service.SERVICE_DISABLED
                        )
                        print(f"Durdurulan servis: {service[0]}")
                        self.logger(f"Durdurulan servis: {service[0]}")
                        stopped_count += 1
                    except Exception as e:
                        print(f"Servis durdurma hatası: {e}")
                        self.logger(f"Servis durdurma hatası: {e}")
            except Exception:
                pass
        
        return stopped_count

    def create_temp_driver(self):
        """
        Geçici bir sürücü oluştur
        
        Returns:
            Oluşturulan sürücü dosyasının yolu
        """
        try:
            # Geçici bir dizin oluştur
            temp_dir = tempfile.mkdtemp()
            self.temp_driver_path = os.path.join(temp_dir, "destroyer_driver.sys")
            
            # Basit bir sürücü şablonu oluştur
            driver_code = b"Driver template for file and process destruction"
            
            with open(self.temp_driver_path, "wb") as f:
                f.write(driver_code)
            
            return self.temp_driver_path
        except Exception as e:
            print(f"Sürücü oluşturma hatası: {e}")
            self.logger(f"Sürücü oluşturma hatası: {e}")
            return None

    def install_temp_driver(self, driver_path):
        """
        Geçici sürücüyü yükle
        
        Args:
            driver_path: Sürücü dosyasının yolu
        
        Returns:
            Yükleme başarılı mı
        """
        try:
            # SCM ile sürücü yükleme
            subprocess.run([
                "sc", "create", "DestroyerTempDriver", 
                "binPath=", driver_path, 
                "type=", "kernel"
            ], check=True)
            
            subprocess.run([
                "sc", "start", "DestroyerTempDriver"
            ], check=True)
            
            return True
        except Exception as e:
            print(f"Sürücü yükleme hatası: {e}")
            self.logger(f"Sürücü yükleme hatası: {e}")
            return False

    def cleanup(self):
        """
        Geçici dosyaları ve sürücüleri temizle
        """
        try:
            # Sürücüyü durdur ve kaldır
            if self.temp_driver_path:
                subprocess.run([
                    "sc", "stop", "DestroyerTempDriver"
                ], check=False)
                
                subprocess.run([
                    "sc", "delete", "DestroyerTempDriver"
                ], check=False)
                
                # Geçici dosyaları sil
                if os.path.exists(self.temp_driver_path):
                    os.unlink(self.temp_driver_path)
                
                # Üst dizini de sil
                temp_dir = os.path.dirname(self.temp_driver_path)
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            print(f"Temizleme hatası: {e}")
            self.logger(f"Temizleme hatası: {e}")

    def forceful_delete(self, file_path):
        """
        Dosyayı zorla silme işlemi
        
        Args:
            file_path: Silinecek dosyanın yolu
        
        Returns:
            Silme işlemi başarılı mı
        """
        try:
            # Dosya/dizin izinlerini değiştir
            try:
                os.chmod(file_path, stat.S_IWRITE)
            except Exception:
                pass
            
            # Dosya veya dizin silme
            if os.path.isdir(file_path):
                # Dizin silme
                shutil.rmtree(file_path, ignore_errors=True)
            else:
                # Dosya silme
                os.remove(file_path)
            
            return not os.path.exists(file_path)
        except Exception as e:
            print(f"Zorla silme hatası: {e}")
            self.logger(f"Zorla silme hatası: {e}")
            return False

class DeletionListWidget(QWidget):
    """
    Dosya/klasör silme listesi için özel widget
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Ana düzen
        layout = QVBoxLayout(self)
        
        # Dosya/klasör tablosu
        self.table = QTableWidget()
        self.table.setColumnCount(3)  # Yol, Durum, İptal Butonu
        self.table.setHorizontalHeaderLabels(["Yol", "Durum", "İşlem"])
        
        # Genişlik ayarları
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 400)  # Yol sütunu
        self.table.setColumnWidth(1, 200)  # Durum sütunu
        self.table.setColumnWidth(2, 150)  # İptal butonu sütunu
        
        # Tema desteği
        self.current_theme = 'light'
        
        # Tablo stil ayarları
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                alternate-background-color: #f0f0f0;
                selection-background-color: #a6a6a6;
            }
            QHeaderView::section {
                background-color: #2196F3;
                color: white;
                padding: 5px;
                border: 1px solid #1976D2;
                font-weight: bold;
            }
        """)
        
        layout.addWidget(self.table)

    def add_path(self, path):
        """
        Tabloya yeni bir yol ekler
        """
        row_count = self.table.rowCount()
        self.table.insertRow(row_count)
        
        # Yol sütunu
        path_item = QTableWidgetItem(path)
        path_item.setFlags(path_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row_count, 0, path_item)
        
        # Durum sütunu
        status_item = QTableWidgetItem("Bekliyor")
        status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row_count, 1, status_item)
        
        # İptal butonu
        cancel_button = QPushButton("İptal Et")
        cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        
        # Her satır için benzersiz lambda fonksiyonu
        cancel_button.clicked.connect(lambda checked, row=row_count: self.cancel_path(row))
        
        # Butonu hücreye yerleştir
        self.table.setCellWidget(row_count, 2, cancel_button)
        
        # Satır yüksekliğini ayarla
        self.table.setRowHeight(row_count, 40)

    def update_path_status(self, path, status):
        """
        Belirli bir yolun durumunu günceller ve dosyaları tablodan çıkarır
        """
        for row in range(self.table.rowCount()):
            path_item = self.table.item(row, 0)
            if path_item and path_item.text() == path:
                # Dosya silindiğinde tablodan çıkar
                if status == 'Silindi':
                    self.table.removeRow(row)
                break

    def cancel_path(self, row):
        """
        Belirli bir satırı iptal eder
        """
        try:
            # Tablodaki yolu al
            path_item = self.table.item(row, 0)
            if path_item:
                path = path_item.text()
                
                # Durumu güncelle
                status_item = self.table.item(row, 1)
                if status_item:
                    status_item.setText("İptal Edildi")
                
                # Ana pencereye yönlendir
                if hasattr(self.parent(), 'handle_path_cancellation'):
                    self.parent().handle_path_cancellation(path)
                else:
                    # Güvenlik için log kaydı
                    logging.warning(f"Path cancellation not handled: {path}")
                
                # Silme listesinden çıkar
                self.table.removeRow(row)
        except Exception as e:
            logging.error(f"Path cancellation error: {e}")

    def get_active_paths(self):
        """
        Henüz silinmemiş veya iptal edilmemiş yolları döndürür
        """
        active_paths = []
        for row in range(self.table.rowCount()):
            status_item = self.table.item(row, 1)
            if status_item and status_item.text() == "Bekliyor":
                path_item = self.table.item(row, 0)
                if path_item:
                    active_paths.append(path_item.text())
        return active_paths

    def toggle_theme(self, theme='light'):
        """
        Temayı değiştirir
        """
        self.current_theme = theme
        if theme == 'light':
            # Açık tema
            self.table.setStyleSheet("""
                QTableWidget {
                    background-color: white;
                    alternate-background-color: #f0f0f0;
                    selection-background-color: #a6a6a6;
                }
                QHeaderView::section {
                    background-color: #2196F3;
                    color: white;
                    padding: 5px;
                    border: 1px solid #1976D2;
                    font-weight: bold;
                }
            """)
        else:
            # Koyu tema
            self.table.setStyleSheet("""
                QTableWidget {
                    background-color: #2c2c2c;
                    alternate-background-color: #3c3c3c;
                    selection-background-color: #505050;
                    color: white;
                }
                QHeaderView::section {
                    background-color: #1976D2;
                    color: white;
                    padding: 5px;
                    border: 1px solid #2196F3;
                    font-weight: bold;
                }
            """)

class ThemeManager:
    THEMES = {
        'light': {
            'background': '#F0F4F8',
            'text': '#2D3748',
            'primary': '#3182CE',
            'secondary': '#4A5568',
            'accent': '#E6FFFA'
        },
        'dark': {
            'background': '#1A202C',
            'text': '#E2E8F0',
            'primary': '#4FD1C5',
            'secondary': '#CBD5E0',
            'accent': '#2D3748'
        },
        'cyberpunk': {
            'background': '#0A0A2A',
            'text': '#00FFFF',
            'primary': '#FF00FF',
            'secondary': '#00FF00',
            'accent': '#FF6B6B'
        }
    }

    @classmethod
    def get_theme(cls, theme_name='light'):
        return cls.THEMES.get(theme_name, cls.THEMES['light'])

class AnimatedMessageBox(QDialog):
    def __init__(self, title, message, theme='light', parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.theme = ThemeManager.get_theme(theme)
        
        layout = QVBoxLayout()
        
        # Animated message label
        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet(f"""
            color: {self.theme['text']};
            font-size: 16px;
            font-weight: bold;
            padding: 20px;
            background: linear-gradient(45deg, {self.theme['primary']}, {self.theme['secondary']});
            border-radius: 15px;
        """)
        
        # Confirm button with animation
        self.confirm_button = QPushButton("Anladım")
        self.confirm_button.setStyleSheet(f"""
            background-color: {self.theme['accent']};
            color: {self.theme['text']};
            border-radius: 10px;
            padding: 10px;
            font-weight: bold;
        """)
        self.confirm_button.clicked.connect(self.accept)
        
        layout.addWidget(self.message_label)
        layout.addWidget(self.confirm_button)
        
        self.setLayout(layout)
        
        # Add fade-in and scale animation
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        
        self.opacity_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.opacity_anim.setDuration(500)
        self.opacity_anim.setStartValue(0)
        self.opacity_anim.setEndValue(1)
        self.opacity_anim.setEasingCurve(QEasingCurve.InOutQuad)
        
        self.scale_anim = QPropertyAnimation(self, b"geometry")
        self.scale_anim.setDuration(500)
        self.scale_anim.setStartValue(QRectF(self.geometry()))
        self.scale_anim.setEndValue(QRectF(self.geometry()))
        self.scale_anim.setEasingCurve(QEasingCurve.OutBounce)
        
        self.anim_group = QParallelAnimationGroup()
        self.anim_group.addAnimation(self.opacity_anim)
        self.anim_group.addAnimation(self.scale_anim)
        
    def showEvent(self, event):
        super().showEvent(event)
        self.anim_group.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor(self.theme['primary']))
        gradient.setColorAt(1, QColor(self.theme['secondary']))
        painter.fillRect(self.rect(), gradient)
        super().paintEvent(event)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Program adı
        self.setWindowTitle("İnatçı Dosya Silici")
        
        # Tema için varsayılan ayar
        self.current_theme = 'light'
        
        # Animasyon için opacity effect
        self.opacity_effect = QGraphicsOpacityEffect(self)
        
        self.initUI()
        
        # Eksik label'ı ekle
        self.remaining_files_label = QLabel("⏳ Kalan Dosya: 0")
        
        # Diğer gerekli düzenlemeler
        self.setup_error_handling()
        
        # İlk tema uygulaması
        self.apply_theme()

    def setup_error_handling(self):
        """
        Hata yakalama ve raporlama mekanizması
        """
        # Global hata yakalayıcı
        sys.excepthook = self.global_exception_handler

    def global_exception_handler(self, exc_type, exc_value, exc_traceback):
        """
        Tüm işletim sistemi genelinde hata yakalama
        """
        # Hata bilgilerini formatla
        error_message = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        
        # Hata iletişim kutusunu oluştur
        error_dialog = AnimatedMessageBox("Kritik Hata", "Beklenmeyen bir hata oluştu!", theme=self.current_theme)
        error_dialog.setModal(True)
        error_dialog.message_label.setText("Beklenmeyen bir hata oluştu!")
        error_dialog.message_label.setWordWrap(True)
        error_dialog.confirm_button.clicked.connect(error_dialog.accept)
        
        # Hata günlüğünü kaydet
        logging.error(error_message)
        
        # Hata iletişim kutusunu göster
        error_dialog.exec_()
        
        # Gerekirse arka plan işlemlerini durdur
        try:
            if hasattr(self, 'delete_worker') and self.delete_worker:
                self.delete_worker.is_cancelled = True  # Set is_cancelled to True
                print("Cancelling operation...")
                self.cancel_button.setEnabled(False)

        except Exception:
            pass

    def initUI(self):
        """
        İnatçı Dosya Silici için modern ve kullanıcı dostu bir arayüz başlatır
        """
        self.resize(1200, 800)  # Daha geniş pencere
        
        # Ana widget ve düzen
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Üst bilgi bölümü
        header_layout = QHBoxLayout()
        
        # Başlık etiketi
        title_label = QLabel("İnatçı Dosya Silici")
        title_label.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: #2C3E50;
            margin-bottom: 10px;
        """)
        header_layout.addWidget(title_label)
        
        # Tema değiştirme butonu
        self.theme_toggle_button = QPushButton("🌈 Light Theme")
        self.theme_toggle_button.clicked.connect(self.cycle_theme)
        self.theme_toggle_button.setToolTip("Temayı değiştir")
        self.theme_toggle_button.setStyleSheet("""
            QPushButton {
                font-size: 20px;
                border: none;
                background-color: transparent;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
                border-radius: 5px;
            }
        """)
        header_layout.addWidget(self.theme_toggle_button)
        
        # Üst bilgi bölümünü ana düzene ekle
        main_layout.addLayout(header_layout)
        
        # Dosya silme bölümü
        file_deletion_layout = QHBoxLayout()
        
        # Sol taraf: Dosya seçim bölümü
        file_selection_widget = QWidget()
        file_selection_layout = QVBoxLayout(file_selection_widget)
        
        # Dosya ve klasör seçim butonları
        file_buttons_layout = QHBoxLayout()
        
        self.start_button = QPushButton("🚀 Silmeyi Başlat")
        self.start_button.clicked.connect(self.start_deletion)
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
        """)
        
        self.add_files_button = QPushButton("📄 Dosya Ekle")
        self.add_files_button.clicked.connect(self.add_files)
        self.add_files_button.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
        """)
        
        self.add_folders_button = QPushButton("📁 Klasör Ekle")
        self.add_folders_button.clicked.connect(self.add_folders)
        self.add_folders_button.setStyleSheet("""
            QPushButton {
                background-color: #2ECC71;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #27AE60;
            }
        """)
        
        file_buttons_layout.addWidget(self.start_button)  
        file_buttons_layout.addWidget(self.add_files_button)
        file_buttons_layout.addWidget(self.add_folders_button)
        
        file_selection_layout.addLayout(file_buttons_layout)
        
        # Dosya listesi tablosu
        self.deletion_list_widget = DeletionListWidget()
        file_selection_layout.addWidget(self.deletion_list_widget)
        
        # Sağ taraf: İşlem kontrol bölümü
        control_widget = QWidget()
        control_layout = QVBoxLayout(control_widget)
        
        # İlerleme çubuğu
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #3498DB;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #3498DB;
                width: 10px;
                margin: 0.5px;
            }
        """)
        
        # Başlat ve İptal butonları
        action_buttons_layout = QHBoxLayout()
        
        cancel_btn = QPushButton("🛑 İptal Et")
        cancel_btn.clicked.connect(self.cancel_deletion)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #95A5A6;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7F8C8D;
            }
        """)
        
        action_buttons_layout.addWidget(cancel_btn)
        
        control_layout.addWidget(self.progress_bar)
        control_layout.addLayout(action_buttons_layout)
        
        # İstatistik etiketleri
        stats_layout = QHBoxLayout()
        
        self.total_files_label = QLabel("📊 Toplam Dosya: 0")
        self.deleted_files_label = QLabel("🗑️ Silinen Dosya: 0")
        self.remaining_files_label = QLabel("⏳ Kalan Dosya: 0")
        
        stats_layout.addWidget(self.total_files_label)
        stats_layout.addWidget(self.deleted_files_label)
        stats_layout.addWidget(self.remaining_files_label)
        
        control_layout.addLayout(stats_layout)
        
        # Ana düzen bölümleri
        file_deletion_layout.addWidget(file_selection_widget)
        file_deletion_layout.addWidget(control_widget)
        
        main_layout.addLayout(file_deletion_layout)
        
        # Merkezi widget ayarla
        self.setCentralWidget(central_widget)
        
        # Tema uygula
        self.apply_theme()

    def cycle_theme(self):
        """
        Tema değişikliği için metot
        """
        themes = ['light', 'dark', 'cyberpunk']
        current_index = themes.index(self.current_theme)
        next_theme = themes[(current_index + 1) % len(themes)]
        
        # Update the theme button text to show current theme
        self.theme_toggle_button.setText(f"🌈 {next_theme.capitalize()} Theme")
        
        self.current_theme = next_theme
        self.apply_theme()

    def apply_theme(self):
        """
        Seçilen temayı tüm arayüze uygula
        """
        theme = ThemeManager.get_theme(self.current_theme)
        
        # Ana pencere arka plan rengi
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {theme['background']};
                color: {theme['text']};
            }}
            QLabel {{
                color: {theme['text']};
            }}
            QWidget {{
                background-color: {theme['background']};
                color: {theme['text']};
            }}
        """)
        
        # Tema butonunu güncelle
        if hasattr(self, 'theme_toggle_button'):
            self.theme_toggle_button.setStyleSheet(f"""
                QPushButton {{
                    font-size: 20px;
                    border: none;
                    background-color: transparent;
                    padding: 5px;
                }}
                QPushButton:hover {{
                    background-color: {theme['primary']};
                    border-radius: 5px;
                }}
            """)
        
        # İlerleme çubuğunu güncelle
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setStyleSheet(f"""
                QProgressBar {{
                    border: 2px solid {theme['primary']};
                    border-radius: 5px;
                    text-align: center;
                }}
                QProgressBar::chunk {{
                    background-color: {theme['primary']};
                    width: 10px;
                    margin: 0.5px;
                }}
            """)
        
        # Başlat ve İptal butonlarını güncelle
        if hasattr(self, 'start_button'):
            self.start_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {theme['accent']};
                    color: {theme['text']};
                    border: none;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {theme['secondary']};
                }}
            """)
        
        if hasattr(self, 'cancel_button'):
            self.cancel_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {theme['accent']};
                    color: {theme['text']};
                    border: none;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {theme['secondary']};
                }}
            """)
        
        # İstatistik etiketlerini güncelle
        if hasattr(self, 'total_files_label'):
            self.total_files_label.setStyleSheet(f"""
                QLabel {{
                    color: {theme['text']};
                    font-size: 18px;
                    padding: 10px;
                    border: 2px solid {theme['primary']};
                    border-radius: 8px;
                    font-weight: bold;
                    min-height: 40px;
                }}
            """)
        
        if hasattr(self, 'deleted_files_label'):
            self.deleted_files_label.setStyleSheet(f"""
                QLabel {{
                    color: {theme['text']};
                    font-size: 18px;
                    padding: 10px;
                    border: 2px solid {theme['primary']};
                    border-radius: 8px;
                    font-weight: bold;
                    min-height: 40px;
                }}
            """)
        
        if hasattr(self, 'remaining_files_label'):
            self.remaining_files_label.setStyleSheet(f"""
                QLabel {{
                    color: {theme['text']};
                    font-size: 18px;
                    padding: 10px;
                    border: 2px solid {theme['primary']};
                    border-radius: 8px;
                    font-weight: bold;
                    min-height: 40px;
                }}
            """)
        
        # Silme listesini güncelle
        if hasattr(self, 'deletion_list_widget'):
            self.deletion_list_widget.toggle_theme(self.current_theme)

    def cancel_deletion(self):
        if hasattr(self, 'delete_worker'):
            self.delete_worker.is_cancelled = True  # Set is_cancelled to True
            print("Cancelling operation...")
            self.cancel_button.setEnabled(False)

    def start_deletion(self):
        """
        Dosya silme işlemini başlatır, kapsamlı kontroller yapar
        """
        try:
            # Standart print ve logging için debug mesajları ekle
            print("start_deletion method called")
            logging.info("Deletion process started")
            
            # Seçilen yolu al
            selected_path = self.path_label.text().strip()
            print(f"Selected path: {selected_path}")
            logging.info(f"Selected path: {selected_path}")
            
            # Yol boş mu kontrol et
            if not selected_path or selected_path == "No path selected":
                print("No path selected")
                logging.warning("No path selected")
                QMessageBox.warning(self, "Uyarı", "Lütfen silmek için bir dosya veya klasör seçin.")
                return
            
            # Yolları normalize et ve kontrol et
            paths = [os.path.normpath(path.strip()) for path in selected_path.split(";")]
            print(f"Normalized paths: {paths}")
            logging.info(f"Normalized paths: {paths}")
            
            # Geçerli yolları kontrol et
            valid_paths = []
            for path in paths:
                if not os.path.exists(path):
                    print(f"Path does not exist: {path}")
                    logging.warning(f"Invalid path: {path}")
                    print(f"Geçersiz yol: {path}")
                    continue
                valid_paths.append(path)
            
            # Hiç geçerli yol yoksa uyar
            if not valid_paths:
                print("No valid paths found")
                logging.error("No valid paths for deletion")
                QMessageBox.warning(self, "Hata", "Silinecek geçerli dosya veya klasör bulunamadı.")
                return
            
            # Kullanıcıdan son onay
            confirm_message = f"Aşağıdaki {len(valid_paths)} yolu silmek istediğinizden emin misiniz?\n\n"
            confirm_message += "\n".join(valid_paths)
            
            reply = QMessageBox.question(
                self, 
                "Silme Onayı", 
                confirm_message, 
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                print("User cancelled deletion")
                logging.info("Deletion cancelled by user")
                return
            
            # İş parçacığını oluştur
            print("Creating DeleteWorker")
            logging.info("Creating DeleteWorker")
            
            # DeleteWorker'ı oluştur
            self.delete_worker = DeleteWorker(";".join(valid_paths))
            
            # Sinyalleri bağla
            print("Connecting worker signals")
            logging.info("Connecting worker signals")
            
            # Sinyalleri güvenli bir şekilde bağla
            try:
                self.delete_worker.log_message.connect(self.log_message)
                self.delete_worker.progress.connect(self.update_progress)
                self.delete_worker.finished.connect(self.deletion_finished)
                self.delete_worker.confirmation_needed.connect(self.confirm_deletion)
                self.delete_worker.result.connect(self.deletion_result)
            except Exception as signal_error:
                print(f"Signal connection error: {signal_error}")
                logging.error(f"Signal connection error: {signal_error}")
                QMessageBox.critical(self, "Hata", f"Sinyal bağlantı hatası: {signal_error}")
                return
            
            # Log temizle
            # self.log_text.clear()
            
            # İş parçacığını başlat
            try:
                print("Starting worker thread")
                logging.info("Starting worker thread")
                self.delete_worker.start()
                print("Worker thread started successfully")
                logging.info("Worker thread started successfully")
            except Exception as start_error:
                print(f"Worker start failed: {start_error}")
                logging.error(f"Worker start failed: {start_error}")
                QMessageBox.critical(self, "Hata", f"İş parçacığı başlatılamadı: {start_error}")
                return
            
            # Butonları güncelle
            self.start_button.setEnabled(False)
            self.cancel_button.setEnabled(True)
            
            # Log mesajı
            log_msg = f"Silme işlemi başlatıldı: {len(valid_paths)} hedef"
            print(log_msg)
            logging.info(log_msg)
        
        except Exception as e:
            # Detaylı hata günlüğü
            error_msg = f"Silme işlemi başlatılamadı: {e}"
            print(error_msg)
            logging.error(error_msg, exc_info=True)
            
            QMessageBox.critical(self, "Hata", error_msg)
            print(error_msg)

    def confirm_deletion(self, message):
        """
        Yüksek koruma seviyeli dosyalar için onay mekanizması
        """
        try:
            reply = AnimatedMessageBox("Yüksek Koruma Seviyesi Uyarısı", message, theme=self.current_theme, parent=self)
            reply.exec_()
            
            if reply.result() == 0:
                # Silme işlemine devam et
                self.delete_worker.run()
            else:
                # İşlemi iptal et
                print("Yüksek koruma seviyeli dosya silme işlemi kullanıcı tarafından iptal edildi.")
                self.deletion_finished()
        
        except Exception as e:
            error_message = f"Onay işleminde hata: {e}"
            QMessageBox.critical(self, "Hata", error_message)
            print(error_message)
            self.deletion_finished()

    def deletion_finished(self):
        """
        Silme işlemi tamamlandığında çağrılan metot
        """
        try:
            # İşlem tamamlandı mesajını ekle
            print("Silme işlemi tamamlandı.")
            # self.log_text.append("Silme işlemi tamamlandı.")
            
            # Progress bar'ı sıfırla
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("%p%")
            
            # Kalan dosya sayısını sıfırla
            self.remaining_files_label.setText("⏳ Kalan Dosya: 0")
            
            # Silme işçisini temizle
            if hasattr(self, 'delete_worker'):
                # Call deletion_result with the result
                result = self.delete_worker.result
                self.deletion_result(result)
                
                self.delete_worker.deleteLater()
                del self.delete_worker
            
            # Butonları yeniden etkinleştir
            self.start_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            
            # Gerekirse dosya listesini temizle
            if hasattr(self, 'deletion_list_widget'):
                self.deletion_list_widget.table.setRowCount(0)
        
        except Exception as e:
            print(f"Silme işlemi sonlandırma hatası: {e}")
            QMessageBox.warning(self, "Hata", f"Silme işlemi sonlandırılırken hata oluştu: {e}")

    def deletion_result(self, result):
        """
        Silme işleminin sonucu
        Kullanıcıya detaylı bilgi göster
        """
        try:
            # Silinen ve başarısız dosyaların sayısını al
            total_files = result.get('total_files', 0)
            deleted_files = result.get('deleted_files', 0)
            failed_files = result.get('failed_files', 0)
            
            # Debug çıktıları
            print(f"Deletion Result - Total: {total_files}, Deleted: {deleted_files}, Failed: {failed_files}")
            
            # Sonuç mesajını hazırla
            if deleted_files > 0:
                message = f"Toplam {total_files} dosyadan {deleted_files} dosya silindi.\n"
                if failed_files > 0:
                    message += f"{failed_files} dosya silinemedi."
                
                # Detaylı silinen dosyaları göster (isteğe bağlı)
                if deleted_files <= 10:  # Çok fazla dosya varsa listelemeden geç
                    message += "\n\nSilinen Dosyalar:\n" + "\n".join(result.get('deleted', []))
            else:
                message = "Hiçbir dosya silinemedi."
            
            # Konsola yazdır
            print(message)
            
            # Arayüzü güncelle
            if hasattr(self, 'progress_bar'):
                self.progress_bar.setValue(100)
                self.progress_bar.setFormat("Tamamlandı %p%")
            
            # Butonları yeniden etkinleştir
            if hasattr(self, 'start_button'):
                self.start_button.setEnabled(True)
            if hasattr(self, 'cancel_button'):
                self.cancel_button.setEnabled(False)
        
        except Exception as e:
            print(f"Sonuç işleme hatası: {e}")
            QMessageBox.warning(None, "Hata", f"Silme sonucu işlenirken hata oluştu: {e}")

    def update_progress(self, stats):
        """
        İlerleme çubuğunu ve etiketleri günceller
        """
        # İlerleme çubuğunu sıfırla
        self.progress_bar.setValue(0)
        
        # İlerleme çubuğunu güncelle
        if stats['total_files'] > 0:
            progress_value = int((stats['deleted_files'] / stats['total_files']) * 100)
            self.progress_bar.setValue(progress_value)
        
        # Dosya istatistik etiketlerini güncelle
        self.total_files_label.setText(f"📊 Toplam Dosya: {stats['total_files']}")
        self.deleted_files_label.setText(f"🗑️ Silinen Dosya: {stats['deleted_files']}")
        self.failed_files_label.setText(f"❌ Başarısız Dosya: {stats['failed_files']}")
        
        # Geçerli dosyayı silinmiş olarak işaretle
        if stats['current_file']:
            self.deletion_list_widget.update_path_status(stats['current_file'], "Silindi")
        
        # Kalan dosya sayısını güncelle
        remaining_files = stats['total_files'] - stats['deleted_files'] - stats['failed_files']
        self.remaining_files_label.setText(f"⏳ Kalan Dosya: {max(0, remaining_files)}")
        
        # Günlük kayıt
        self.log_message(f"Silme İşlemi: {stats['deleted_files']}/{stats['total_files']} dosya silindi")

    def log_message(self, message):
        print(message)

    def handle_path_cancellation(self, path):
        """
        Kullanıcı tarafından iptal edilen yolu işler
        """
        # Silme işlemini iptal etmek için gerekli mantığı ekle
        if hasattr(self, 'delete_worker'):
            # Eğer worker çalışıyorsa, iptal edilecek yolu işaretle
            self.delete_worker.cancelled_paths.add(path)
            
            # Silme listesindeki durumu güncelle
            self.deletion_list_widget.update_path_status(path, "İptal Edildi")

    def add_files(self):
        """
        Open file dialog to add files for deletion and reset the deletion list
        """
        # Clear existing deletion list and reset progress
        self.deletion_list_widget.table.setRowCount(0)
        
        files, _ = QFileDialog.getOpenFileNames(self, "Select Files to Delete", "", "All Files (*)")
        for file in files:
            self.deletion_list_widget.add_path(file)
        
        # Reset progress indicators
        self.progress_bar.setValue(0)
        self.remaining_files_label.setText("⏳ Kalan Dosya: " + str(len(files)))
        self.update_file_statistics()

    def add_folders(self):
        """
        Open folder dialog to add folders for deletion and reset the deletion list
        """
        # Clear existing deletion list and reset progress
        self.deletion_list_widget.table.setRowCount(0)
        
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Delete")
        if folder:
            self.deletion_list_widget.add_path(folder)
        
        # Reset progress indicators
        self.progress_bar.setValue(0)
        self.remaining_files_label.setText("⏳ Kalan Klasör: 1")
        self.update_file_statistics()

    def update_file_statistics(self):
        """
        Update file-related statistics labels
        """
        active_paths = self.deletion_list_widget.get_active_paths()
        self.total_files_label.setText(f"📊 Toplam Dosya: {len(active_paths)}")
        self.remaining_files_label.setText(f"⏳ Kalan Dosya: {len(active_paths)}")

    def start_deletion(self):
        """
        Start the file deletion process
        """
        active_paths = self.deletion_list_widget.get_active_paths()
        if not active_paths:
            QMessageBox.warning(self, "Warning", "No files or folders selected for deletion.")
            return

        # Disable start button during deletion
        self.start_button.setEnabled(False)
        self.add_files_button.setEnabled(False)
        self.add_folders_button.setEnabled(False)

        # Başlangıç zamanını kaydet
        self.start_time = time.time()

        # Start deletion worker
        self.delete_worker = DeleteWorker(active_paths)
        self.delete_worker.progress.connect(self.update_progress)
        self.delete_worker.finished.connect(self.deletion_finished)
        self.delete_worker.result.connect(self.deletion_result)
        self.delete_worker.start()

    def update_progress(self, stats):
        """
        Update progress bar and labels with deletion statistics
        """
        total_files = stats.get('total_files', 0)
        deleted_files = stats.get('deleted_files', 0)
        failed_files = stats.get('failed_files', 0)
        elapsed_time = stats.get('elapsed_time', 0)
        
        # Update progress bar
        if total_files > 0:
            progress_percent = int((deleted_files / total_files) * 100)
            self.progress_bar.setValue(progress_percent)

        # Update labels
        self.total_files_label.setText(f"📊 Toplam Dosya: {total_files}")
        self.deleted_files_label.setText(f"🗑️ Deleted Files: {deleted_files}")
        self.remaining_files_label.setText(f"⏳ Remaining Files: {total_files - deleted_files}")
        
        # Format elapsed time
        hours, remainder = divmod(int(elapsed_time), 3600)
        minutes, seconds = divmod(remainder, 60)
        print(f"Geçen Süre: {hours:02d}:{minutes:02d}:{seconds:02d}")
        
        # Tüm dosyalar silindiğinde sonlandır
        if deleted_files + failed_files >= total_files:
            self.deletion_finished()

    def deletion_finished(self):
        """
        Handle completion of deletion process
        """
        self.start_button.setEnabled(True)
        self.add_files_button.setEnabled(True)
        self.add_folders_button.setEnabled(True)
        
        # Show completion message
        # Removed the QMessageBox.information call here

    def cancel_deletion(self):
        """
        Cancel ongoing deletion process
        """
        if hasattr(self, 'delete_worker'):
            self.delete_worker.is_cancelled = True
        
        # Reset UI
        self.progress_bar.setValue(0)
        self.start_button.setEnabled(True)
        self.add_files_button.setEnabled(True)
        self.add_folders_button.setEnabled(True)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()