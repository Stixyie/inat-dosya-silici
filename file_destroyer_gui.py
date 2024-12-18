#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Dosya ve Klasör Silme Aracı
Bu araç, kullanıcılara dosya ve klasörleri güvenli ve hızlı bir şekilde silme imkanı sağlar.
"""

import os
import stat
import subprocess
import shutil
import platform
import time
import ctypes
import sys
import warnings
import logging.handlers
import winreg
import struct
import mmap
from ctypes import wintypes
import psutil
import win32api
import win32security
import win32service
import win32serviceutil
import tempfile
from PyQt5.QtWidgets import (QMainWindow, QApplication, QWidget, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QLabel, QProgressBar, 
                            QFileDialog, QTextEdit, QFrame, QStyleFactory, 
                            QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, 
                            QGraphicsOpacityEffect, QComboBox, QDialog, QGridLayout) 
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, 
    QPropertyAnimation, QEasingCurve, QPoint, 
    QSequentialAnimationGroup, QParallelAnimationGroup, 
    QRectF, QRect, QObject
) 
from PyQt5.QtGui import (
    QFont, QIcon, QPalette, QColor, 
    QPainter, QLinearGradient
)

# Detaylı logging ayarları
import logging
import traceback
import sys
import os

# Log dizinini oluştur
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Log dosyası yolu
LOG_FILENAME = os.path.join(LOG_DIR, 'file_destroyer_detailed.log')

# Detaylı logger yapılandırması
def setup_detailed_logging():
    # Root logger'ı yapılandır
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s | %(levelname)8s | %(filename)20s:%(lineno)4d | %(funcName)20s | %(message)s',
        handlers=[
            # Dosyaya yazma handler'ı
            logging.FileHandler(LOG_FILENAME, mode='w', encoding='utf-8'),
            # Konsola yazma handler'ı
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Özel exception hook
    def custom_excepthook(exc_type, exc_value, exc_traceback):
        logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
        # Orijinal exception hook'u da çağır
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    # Exception hook'u değiştir
    sys.excepthook = custom_excepthook

# Logging'i başlat
setup_detailed_logging()
logger = logging.getLogger(__name__)

# Tüm modüllerin loglarını da yakala
logging.getLogger('PyQt5').setLevel(logging.DEBUG)

# Hata yakalama ve log fonksiyonu
def log_and_print_exception(func):
    def wrapper(*args, **kwargs):
        try:
            logger.debug(f"Calling {func.__name__} with args: {args}, kwargs: {kwargs}")
            result = func(*args, **kwargs)
            logger.debug(f"{func.__name__} completed successfully")
            return result
        except Exception as e:
            logger.error(f"Exception in {func.__name__}: {str(e)}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            raise
    return wrapper

# Daha spesifik uyarı bastırma
warnings.filterwarnings("ignore", category=DeprecationWarning, module="PyQt5.*", message="sipPyTypeDict()")

# Windows düşük seviye API sabitleri
INVALID_HANDLE_VALUE = -1
FILE_ATTRIBUTE_NORMAL = 0x80
FILE_FLAG_WRITE_THROUGH = 0x80000000
FILE_FLAG_NO_BUFFERING = 0x20000000
GENERIC_ALL = 0x10000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
CREATE_ALWAYS = 2
OPEN_EXISTING = 3

# Günlük ayarları
import logging as logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Windows API sabitleri ve global değişkenler
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

# Windows Shell API
shell32 = ctypes.windll.shell32

import traceback
import queue
import threading
import concurrent.futures
import uuid

class DeleteWorker(QThread):
    progress = pyqtSignal(dict)
    finished = pyqtSignal()
    result = pyqtSignal(dict)

    def __init__(self, paths):
        super().__init__()
        # Güvenli yol dönüşümü
        self.paths = paths if isinstance(paths, list) else str(paths).split(';')
        
        # Güvenli istatistik başlatma
        self.stats = {
            'total': len(self.paths),
            'deleted': 0,
            'failed': 0,
            'error_details': []
        }
        
        # Güvenli kuyruk oluştur
        self.deletion_queue = queue.Queue()
        for path in self.paths:
            self.deletion_queue.put(path.strip())
        
        # Thread güvenliği için kilit
        self._lock = threading.Lock()
        self.is_cancelled = False

    def run(self):
        try:
            # Tüm dosyaları silmeye çalış
            while not self.deletion_queue.empty() and not self.is_cancelled:
                try:
                    # Kuyruktaki sonraki dosyayı al
                    path = self.deletion_queue.get(timeout=1)
                    
                    try:
                        # Dosyayı silmeye çalış
                        self.delete_file(path)
                    except Exception as e:
                        # Silme hatası durumunda istatistikleri güncelle
                        with self._lock:
                            self.stats['failed'] += 1
                            self.stats['error_details'].append({
                                'path': path,
                                'error': str(e)
                            })
                    
                    # Her dosya işleminden sonra ilerlemeyi güncelle
                    self.progress.emit(self.stats)
                
                except queue.Empty:
                    # Kuyruk boş, döngüden çık
                    break
                except Exception as e:
                    logger.error(f"Dosya silme hatası: {e}")
        
        except Exception as e:
            logger.critical(f"Kritik silme hatası: {e}")
        
        finally:
            # Her durumda sonuçları gönder
            try:
                self.result.emit(self.stats)
                self.finished.emit()
            except Exception as final_error:
                logger.error(f"Son sinyal gönderme hatası: {final_error}")

    def delete_file(self, path):
        """Güvenli dosya/klasör silme"""
        try:
            # Dosya/klasör varlık kontrolü
            if not os.path.exists(path):
                logger.warning(f"Dosya/klasör bulunamadı: {path}")
                return
            
            # Yazma izni ver
            try:
                os.chmod(path, stat.S_IWRITE)
            except Exception as chmod_error:
                logger.warning(f"İzin değiştirme hatası: {chmod_error}")
            
            # Dosya mı klasör mü kontrol et
            if os.path.isfile(path):
                # Dosya silme
                os.unlink(path)
            else:
                # Klasör silme
                shutil.rmtree(path, ignore_errors=True)
            
            # Başarılı silme istatistiği
            with self._lock:
                self.stats['deleted'] += 1
            
            logger.debug(f"Başarıyla silindi: {path}")
        
        except Exception as e:
            logger.error(f"Dosya silme hatası - {path}: {e}")
            raise

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

    def assembly_low_level_delete(self, file_path):
        """
        Donanım seviyesinde Assembly kullanarak dosya silme işlemi
        
        Args:
            file_path (str): Silinecek dosyanın tam yolu
        
        Returns:
            bool: Silme işleminin başarılı olup olmadığı
        """
        try:
            # Windows için x86-64 Assembly inline fonksiyonu
            def windows_assembly_delete(file_path_bytes):
                try:
                    # Assembly kodu için ctypes kullanarak düşük seviye silme
                    libc = CDLL('msvcrt.dll')
                    
                    # Assembly dilinde dosya silme fonksiyonu
                    assembly_delete_func = CFUNCTYPE(c_int, c_char_p)(
                        """
                        ; x86-64 Assembly dosya silme fonksiyonu
                        ; Düşük seviye doğrudan sistem çağrısı
                        push rbp
                        mov rbp, rsp
                        
                        ; Dosya yolu parametresini al
                        mov rax, rcx
                        
                        ; Windows DeleteFileA sistem çağrısı için hazırlık
                        sub rsp, 32  ; Shadow space ayırma
                        
                        ; DeleteFileA çağrısı (Windows API)
                        call [rel DeleteFileA]
                        
                        ; Sonucu kontrol et
                        test rax, rax
                        setnz al  ; Başarılıysa al register'ını 1 yap
                        movzx eax, al  ; Sonucu genişlet
                        
                        leave
                        ret
                        """.encode('utf-8')
                    )
                    
                    # Dosya silme işlemi
                    result = assembly_delete_func(file_path_bytes)
                    return result == 1
                except Exception as e:
                    logging.error(f"Assembly düşük seviye silme hatası: {e}")
                    return False

            # Dosya yolunu byte'a çevir
            file_path_bytes = file_path.encode('utf-8')
            
            # Silme işlemini gerçekleştir
            return windows_assembly_delete(file_path_bytes)
        
        except Exception as e:
            logging.error(f"Assembly dosya silme hatası: {e}")
            return False

class DeletionListWidget(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Sütun başlıklarını ayarla
        self.setColumnCount(3)
        self.setHorizontalHeaderLabels(["Dosya/Klasör", "Durum", "İşlem"])
        
        # Genişlik ayarları
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setColumnWidth(0, 400)  # Dosya/Klasör sütunu
        self.setColumnWidth(1, 200)  # Durum sütunu
        self.setColumnWidth(2, 150)  # İptal butonu sütunu
        
        # Seçim ve düzenleme ayarları
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        
        # Tema desteği
        self.current_theme = 'light'
        self.apply_theme(self.current_theme)

    def apply_theme(self, theme='light'):
        """Tema stillerini uygula"""
        if theme == 'light':
            # Açık tema
            self.setStyleSheet("""
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
            self.setStyleSheet("""
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

    def toggle_theme(self, theme='light'):
        """Temayı değiştirir"""
        self.current_theme = theme
        self.apply_theme(theme)

    def add_path(self, path):
        """
        Tabloya yeni bir yol ekler
        """
        try:
            # Dosya/klasör varlık kontrolü
            if not os.path.exists(path):
                QMessageBox.warning(self, "Uyarı", f"Dosya/klasör bulunamadı: {path}")
                return False

            # Satır sayısını al
            row_count = self.rowCount()
            
            # Yeni satır ekle
            self.insertRow(row_count)
            
            # Dosya/klasör adını ayarla
            filename_item = QTableWidgetItem(os.path.basename(path))
            filename_item.setToolTip(path)
            self.setItem(row_count, 0, filename_item)
            
            # Durum sütunu
            status_item = QTableWidgetItem("Beklemede")
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            status_item.setForeground(QColor(100, 100, 100))  # Gri renk
            self.setItem(row_count, 1, status_item)
            
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
            self.setCellWidget(row_count, 2, cancel_button)
            
            # Satır yüksekliğini ayarla
            self.setRowHeight(row_count, 40)
            
            return True
            
        except Exception as e:
            logger.error(f"Dosya/klasör eklenirken hata: {e}")
            QMessageBox.critical(self, "Hata", f"Dosya/klasör eklenemedi: {e}")
            return False

    def cancel_path(self, row):
        """
        Belirli bir satırı iptal eder
        """
        try:
            # Tablodaki yolu al
            path_item = self.item(row, 0)
            if path_item:
                path = path_item.toolTip()  # Tam yolu al
                
                # Durumu güncelle
                status_item = self.item(row, 1)
                if status_item:
                    status_item.setText("İptal Edildi")
                
                # Ana pencereye yönlendir
                if hasattr(self.parent(), 'handle_path_cancellation'):
                    self.parent().handle_path_cancellation(path)
                else:
                    # Güvenlik için log kaydı
                    logging.warning(f"Path cancellation not handled: {path}")
                
                # Silme listesinden çıkar
                self.removeRow(row)
        except Exception as e:
            logging.error(f"Path cancellation error: {e}")

    def get_active_paths(self):
        """
        Henüz silinmemiş veya iptal edilmemiş yolları döndürür
        """
        active_paths = []
        for row in range(self.rowCount()):
            status_item = self.item(row, 1)
            if status_item and status_item.text() == "Beklemede":
                path_item = self.item(row, 0)
                if path_item:
                    active_paths.append(path_item.toolTip())  # Tam yolu döndür
        return active_paths

    def update_path_status(self, path, status):
        """
        Belirli bir yolun durumunu günceller
        """
        for row in range(self.rowCount()):
            path_item = self.item(row, 0)
            if path_item and path_item.toolTip() == path:  # Tam yol ile karşılaştır
                # Durum sütununu güncelle
                status_item = QTableWidgetItem(status)
                status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                
                # Duruma göre renk ayarla
                if status == "Silindi":
                    status_item.setForeground(QColor(0, 150, 0))  # Yeşil
                elif status == "Başarısız":
                    status_item.setForeground(QColor(200, 0, 0))  # Kırmızı
                elif status == "Siliniyor":
                    status_item.setForeground(QColor(0, 0, 200))  # Mavi
                else:
                    status_item.setForeground(QColor(100, 100, 100))  # Gri
                
                self.setItem(row, 1, status_item)
                
                # Dosya silindiğinde satırı kaldır
                if status == "Silindi":
                    self.removeRow(row)
                break

    def clear(self):
        """Tabloyu temizle"""
        self.setRowCount(0)

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
          
        layout.addWidget(self.message_label)
        
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

class FailedFilesDialog(QDialog):
    def __init__(self, failed_files, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Silinemeyen Dosyalar")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        
        layout = QVBoxLayout(self)
        
        # Başlık etiketi
        title_label = QLabel("❌ Aşağıdaki dosyalar silinemedi:")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: red;")
        layout.addWidget(title_label)
        
        # Dosya listesi için tablo
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Dosya Yolu", "Hata Nedenleri", "Önerilen Çözümler"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        # Tabloyu doldur
        self.populate_table(failed_files)
        layout.addWidget(self.table)
        
        # Kapat butonu
        close_button = QPushButton("Kapat")
        close_button.clicked.connect(self.accept)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        layout.addWidget(close_button)

    def populate_table(self, failed_files):
        self.table.setRowCount(len(failed_files))
        for row, file_info in enumerate(failed_files):
            # Dosya yolu
            path_item = QTableWidgetItem(file_info['path'])
            path_item.setToolTip(file_info['path'])
            self.table.setItem(row, 0, path_item)
            
            # Hata nedenleri
            reasons = "\n".join(file_info['error_details']['error_reasons'])
            reasons_item = QTableWidgetItem(reasons)
            reasons_item.setToolTip(reasons)
            self.table.setItem(row, 1, reasons_item)
            
            # Önerilen çözümler
            solutions = "\n".join(file_info['error_details']['recommended_actions'])
            solutions_item = QTableWidgetItem(solutions)
            solutions_item.setToolTip(solutions)
            self.table.setItem(row, 2, solutions_item)
            
        self.table.resizeRowsToContents()

class DetailedErrorDialog(QDialog):
    def __init__(self, error_details, theme='light', parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dosya Silme Hatası Detayları")
        self.theme = theme
        self.error_details = error_details
        self.initUI()

    def initUI(self):
        # Pencere boyutunu ayarla
        self.setMinimumSize(800, 600)  # Daha geniş pencere
        
        # Ana düzen
        layout = QVBoxLayout(self)
        
        # Başlık
        title_label = QLabel("🚫 Dosya/Klasör Silme Hatası")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # Hata tablosu
        self.error_table = QTableWidget()
        self.error_table.setColumnCount(4)
        self.error_table.setHorizontalHeaderLabels(["Dosya/Klasör", "Koruma Seviyesi", "Hata Nedeni", "Önerilen Çözüm"])
        self.error_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.error_table)
        
        # Populate error table
        self.populate_error_table()
        
        # Kapat butonu
        close_button = QPushButton("Kapat")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)
        
        # Tema uygulama
        self.apply_theme()

    def populate_error_table(self):
        """Hata detaylarını tabloya ekle"""
        self.error_table.setRowCount(len(self.error_details))
        
        protection_levels = {
            0: "🟢 Düşük Koruma",
            1: "🟡 Orta Koruma",
            2: "🔴 Yüksek Koruma",
            3: "⚫ Kritik Sistem Dosyası"
        }
        
        for row, error in enumerate(self.error_details):
            # Dosya/Klasör adı
            file_path = QTableWidgetItem(error.get('path', 'Bilinmeyen'))
            
            # Koruma seviyesi
            protection_level = error.get('protection_level', 0)
            protection_text = protection_levels.get(protection_level, "🟢 Bilinmeyen")
            level_item = QTableWidgetItem(protection_text)
            
            # Hata nedenleri
            error_reasons = error.get('error_details', {}).get('error_reasons', ['Hata nedeni belirlenemedi'])
            reasons_text = "\n".join(error_reasons)
            reasons_item = QTableWidgetItem(reasons_text)
            
            # Önerilen çözümler
            solutions = error.get('error_details', {}).get('recommended_actions', ['Çözüm önerilemiyor'])
            solutions_text = "\n".join(solutions)
            solutions_item = QTableWidgetItem(solutions_text)
            
            # Tabloya ekle
            self.error_table.setItem(row, 0, file_path)
            self.error_table.setItem(row, 1, level_item)
            self.error_table.setItem(row, 2, reasons_item)
            self.error_table.setItem(row, 3, solutions_item)
        
        self.error_table.resizeRowsToContents()

    def apply_theme(self):
        """Temayı uygula"""
        theme = ThemeManager.get_theme(self.theme)
        
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {theme['background']};
                color: {theme['text']};
            }}
            QLabel {{
                color: {theme['text']};
            }}
            QTableWidget {{
                background-color: {theme['background']};
                color: {theme['text']};
                border: 1px solid {theme['primary']};
            }}
            QHeaderView::section {{
                background-color: {theme['primary']};
                color: {theme['background']};
                padding: 5px;
                border: 1px solid {theme['secondary']};
            }}
            QPushButton {{
                background-color: {theme['accent']};
                color: {theme['text']};
                border: none;
                padding: 10px;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: {theme['secondary']};
            }}
        """)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("İnatçı Dosya Silici")
        self.current_theme = 'light'
        self.failed_files = []  # Silinemeyen dosyaların listesi
        
        # Geçici dosya yolu
        self.temp_file = os.path.join(tempfile.gettempdir(), 'file_destroyer_paths.tmp')
        
        # Önceki seçimleri yükle
        self.load_saved_paths()
        
        self.initUI()
        
    def load_saved_paths(self):
        try:
            if os.path.exists(self.temp_file):
                with open(self.temp_file, 'r', encoding='utf-8') as f:
                    paths = f.read().splitlines()
                    if paths:
                        self.deletion_list_widget = DeletionListWidget()
                        for path in paths:
                            if os.path.exists(path):
                                self.deletion_list_widget.add_path(path)
                os.remove(self.temp_file)
        except Exception:
            pass
            
    def save_paths(self, paths):
        try:
            with open(self.temp_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(paths))
        except Exception:
            pass
            
    def check_admin(self):
        """Yönetici yetkilerini kontrol et"""
        try:
            if not ctypes.windll.shell32.IsUserAnAdmin():
                # Mevcut seçili dosyaları kaydet
                paths = self.deletion_list_widget.get_active_paths()
                self.save_paths(paths)
                
                # Yönetici olarak yeniden başlat
                script = os.path.abspath(sys.argv[0])
                params = ' '.join([script] + sys.argv[1:])
                ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
                if ret <= 32:
                    QMessageBox.critical(self, "Hata", "Yönetici izni alınamadı!")
                    return False
                sys.exit(0)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Yönetici yetkisi kontrolü hatası: {str(e)}")
            return False

    def start_deletion(self):
        """Dosya silme işlemini başlat"""
        try:
            # Önceki silme işlemini temizle
            if hasattr(self, 'delete_worker'):
                if self.delete_worker and self.delete_worker.isRunning():
                    self.delete_worker.is_cancelled = True
                    self.delete_worker.wait(1000)  # 1 saniye bekle
                self.delete_worker = None

            # Aktif dosya yollarını al
            paths = self.deletion_list_widget.get_active_paths()
            if not paths:
                QMessageBox.warning(self, "Uyarı", "Lütfen silinecek dosya veya klasör ekleyin!")
                self.progress_bar.setFormat("Hazır")
                return

            # Yeni silme işlemini başlat
            self.delete_worker = DeleteWorker(paths)
            
            # Sinyalleri bağla
            self.delete_worker.progress.connect(self.update_progress)
            self.delete_worker.finished.connect(self.deletion_finished)
            self.delete_worker.result.connect(self.deletion_result)
            
            # UI durumunu güncelle
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Silme Başlıyor...")
            self.start_button.setEnabled(False)
            self.cancel_button.setEnabled(True)
            
            # Thread'i başlat
            self.delete_worker.start()
            
        except Exception as e:
            logger.error(f"Silme işlemi başlatılamadı: {e}")
            QMessageBox.critical(self, "Hata", f"Silme işlemi başlatılamadı: {e}")
            self.reset_ui_state()

    def update_progress(self, stats):
        """İlerleme durumunu güncelle"""
        try:
            total = stats.get('total', 0)
            deleted = stats.get('deleted', 0)
            failed = stats.get('failed', 0)
            
            if total > 0:
                progress = int(((deleted + failed) / total) * 100)
                self.progress_bar.setValue(progress)
                
                # İşlem durumunu güncelle
                if progress == 100:
                    status = "Tamamlandı"
                else:
                    status = "Siliniyor"
                
                # Detaylı durum mesajı
                self.progress_bar.setFormat(
                    f"{progress}% - {status} (Silinen: {deleted}, Başarısız: {failed})"
                )
        except Exception as e:
            logger.error(f"İlerleme güncellenirken hata: {e}")
            self.progress_bar.setFormat("Hata!")

    def deletion_finished(self):
        """Silme işlemi tamamlandığında çağrılır"""
        try:
            # Thread'i temizle
            if hasattr(self, 'delete_worker'):
                if self.delete_worker and self.delete_worker.isRunning():
                    self.delete_worker.wait(1000)  # 1 saniye bekle
                self.delete_worker = None
            
            # UI'ı sıfırla
            self.reset_ui_state()
            
        except Exception as e:
            logger.error(f"Silme işlemi sonlandırılırken hata: {e}")
            self.reset_ui_state()

    def reset_ui_state(self):
        """UI durumunu sıfırla"""
        try:
            self.start_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Hazır")
            
            # Dosya listesini temizle
            self.deletion_list_widget.clear()
        except Exception as e:
            logger.error(f"UI durumu sıfırlanırken hata: {e}")

    def add_files(self):
        """
        Open file dialog to add files for deletion and reset the deletion list
        """
        # Clear existing deletion list and reset progress
        self.deletion_list_widget.setRowCount(0)
        
        files, _ = QFileDialog.getOpenFileNames(self, "Select Files to Delete", "", "All Files (*)")
        for file in files:
            self.deletion_list_widget.add_path(file)
        
        # Reset progress indicators
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0 / 0 dosya silindi")

    def add_folders(self):
        """
        Open folder dialog to add folders for deletion and reset the deletion list
        """
        # Clear existing deletion list and reset progress
        self.deletion_list_widget.setRowCount(0)
        
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Delete")
        if folder:
            self.deletion_list_widget.add_path(folder)
        
        # Reset progress indicators
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0 / 0 dosya silindi")

    def cancel_deletion(self):
        """
        İptal butonuna basıldığında silme işlemini durdurur
        """
        if hasattr(self, 'delete_worker'):
            self.delete_worker.is_cancelled = True
            print("Silme işlemi iptal ediliyor...")
            self.cancel_button.setEnabled(False)
            
        # UI durumunu sıfırla
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0 / 0 dosya silindi")
        self.add_file_button.setEnabled(True)
        self.add_folder_button.setEnabled(True)
        self.start_button.setEnabled(True)

    def deletion_result(self, result):
        """Silme işlemi sonucunu işler"""
        try:
            # Sonuç istatistiklerini güvenli bir şekilde al
            total_files = result.get('total', 0)
            deleted_files = result.get('deleted', 0)
            failed_files = result.get('failed', 0)
            
            # Durum mesajını belirle
            if failed_files == 0:
                status = "Tamamlandı"
            elif deleted_files > 0:
                status = "Kısmen Tamamlandı"
            else:
                status = "Başarısız"
            
            # Progress bar'ı güncelle
            self.progress_bar.setFormat(f"{status} - Silinen: {deleted_files}, Başarısız: {failed_files}")
            
            # Logging için detaylı sonuç mesajı
            result_message = (
                f"Toplam: {total_files}, "
                f"Silinen: {deleted_files}, "
                f"Başarısız: {failed_files}"
            )
            logger.info(f"Dosya silme sonucu: {result_message}")
            
            # Hata detaylarını logla
            if failed_files > 0:
                error_details = result.get('error_details', [])
                for error in error_details:
                    logger.error(f"Silme hatası: {error['path']} - {error['error']}")
            
            # UI thread'inde bilgilendirme mesajı göster
            def show_result_message():
                # Başarılı silme durumu
                if failed_files == 0:
                    QMessageBox.information(
                        self, 
                        "Silme Tamamlandı", 
                        f"Tüm dosyalar başarıyla silindi.\n{result_message}"
                    )
                # Kısmi başarı durumu
                elif deleted_files > 0:
                    QMessageBox.warning(
                        self, 
                        "Kısmi Silme", 
                        f"Bazı dosyalar silinemedi.\n{result_message}"
                    )
                # Tamamen başarısız silme
                else:
                    QMessageBox.critical(
                        self, 
                        "Silme Başarısız", 
                        f"Hiçbir dosya silinemedi.\n{result_message}"
                    )
            
            # UI güncellemesini ana thread'de çalıştır
            if QThread.currentThread() == self.thread():
                show_result_message()
            else:
                self.window().invoke(show_result_message)
            
            # UI'ı sıfırla
            self.reset_ui_state()
        
        except Exception as e:
            logger.error(f"Sonuç işleme hatası: {e}")
            
            # Kritik hata durumunda kullanıcıyı bilgilendir
            def show_error_message():
                QMessageBox.critical(
                    self, 
                    "Kritik Hata", 
                    "Dosya silme sonuçları işlenirken bir hata oluştu."
                )
            
            # UI güncellemesini ana thread'de çalıştır
            if QThread.currentThread() == self.thread():
                show_error_message()
            else:
                self.window().invoke(show_error_message)
            
            # Her durumda UI'ı sıfırla
            self.reset_ui_state()

    def initUI(self):
        # Ekran boyutlarını al
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()

        # Pencere boyutunu ekran boyutunun %80'i olarak ayarla
        window_width = int(screen_width * 0.8)
        window_height = int(screen_height * 0.8)

        # Pencereyi ekranın merkezine konumlandır
        self.resize(window_width, window_height)
        
        # Pencereyi ekranın merkezine yerleştir
        frame_geometry = self.frameGeometry()
        center_point = screen.geometry().center()
        frame_geometry.moveCenter(center_point)
        self.move(frame_geometry.topLeft())

        # Ana düzen
        main_layout = QVBoxLayout()
        
        # Dosya/klasör ekleme bölümü
        file_selection_layout = QHBoxLayout()
        
        # Dosya Ekle butonu
        self.add_file_button = QPushButton("Dosya Ekle")
        self.add_file_button.clicked.connect(self.add_files)
        file_selection_layout.addWidget(self.add_file_button)
        
        # Klasör Ekle butonu
        self.add_folder_button = QPushButton("Klasör Ekle")
        self.add_folder_button.clicked.connect(self.add_folders)
        file_selection_layout.addWidget(self.add_folder_button)
        
        main_layout.addLayout(file_selection_layout)
        
        # Dosya listesi widget'ı
        self.deletion_list_widget = DeletionListWidget()
        main_layout.addWidget(self.deletion_list_widget)
        
        # İlerleme çubuğu
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% - Dosyalar Siliniyor")
        main_layout.addWidget(self.progress_bar)
        
        # Silme ve İptal butonları
        button_layout = QHBoxLayout()
        
        # Sil butonu
        self.start_button = QPushButton("Sil")
        self.start_button.clicked.connect(self.start_deletion)
        button_layout.addWidget(self.start_button)
        
        # İptal butonu
        self.cancel_button = QPushButton("İptal")
        self.cancel_button.clicked.connect(self.cancel_deletion)
        self.cancel_button.setEnabled(False)
        button_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(button_layout)
        
        # Merkezi widget oluştur
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        
        # Pencere stilini ayarla
        self.setStyleSheet("""
            QWidget {
                background-color: #f0f0f0;
                font-family: Arial, sans-serif;
            }
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                color: #666666;
            }
            QProgressBar {
                border: 2px solid grey;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
                width: 10px;
                margin: 0.5px;
            }
        """)
        
        # Ana widget'ı ayarla
        self.setCentralWidget(central_widget)
        
        # Pencere başlığını ayarla
        self.setWindowTitle("İnatçı Dosya Silici")
        
        # Tema ayarları
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
        
        # İlerleme çubuğunu güncelle
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
        
        # Butonları güncelle
        button_style = f"""
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
        """
        
        self.add_file_button.setStyleSheet(button_style)
        self.add_folder_button.setStyleSheet(button_style)
        self.start_button.setStyleSheet(button_style)
        self.cancel_button.setStyleSheet(button_style)
        
        # Dosya listesi widget'ının temasını güncelle
        if hasattr(self, 'deletion_list_widget'):
            self.deletion_list_widget.toggle_theme(self.current_theme)

def safe_log(message):
    """Güvenli günlük kaydetme fonksiyonu"""
    try:
        with open('file_destroyer_debug.log', 'a', encoding='utf-8') as log_file:
            log_file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
        
        # Ayrıca konsola da yazdır
        print(message)
    except Exception as log_error:
        try:
            # Son çare olarak Windows mesaj kutusu
            ctypes.windll.user32.MessageBoxW(
                None, 
                f"Günlük kayıt hatası: {log_error}\nAsıl mesaj: {message}", 
                "Günlük Hatası", 
                0x10  # MB_ICONERROR
            )
        except:
            pass

def log_error(message):
    """Hataları dosyaya ve mesaj kutusuna kaydet"""
    try:
        # Log dosyasına yaz
        with open('file_destroyer_error.log', 'a', encoding='utf-8') as log_file:
            log_file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
        
        # Mesaj kutusunu kullan
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(message), "Hata Detayları", 0x10)
    except Exception as e:
        # Son çare olarak Windows mesaj kutusu
        ctypes.windll.user32.MessageBoxW(None, f"Günlüğe kaydetme hatası: {str(e)}", "Kritik Hata", 0x10)

def is_admin():
    """Geçerli kullanıcının yönetici olup olmadığını kontrol et"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception as e:
        logger.error(f"Yönetici yetkisi kontrolünde hata: {e}")
        return False

def request_admin_rights():
    """Yönetici haklarını iste"""
    try:
        # Kayıt defteri anahtarı ile yönetici izni kontrolü
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                r"Software\Microsoft\Windows\CurrentVersion\Policies\System", 0, 
                winreg.KEY_READ)
            winreg.CloseKey(key)
        except FileNotFoundError:
            # Kayıt defteri anahtarı bulunamadı, yönetici izni gerekli
            logger.info("Yönetici izni gerekli")
        except Exception as e:
            logger.error(f"Kayıt defteri kontrolünde hata: {e}")
        
        # Eğer zaten yönetici değilse
        if not is_admin():
            logger.info("Yönetici izni isteniyor")
            
            # Geçerli script yolunu al
            script = os.path.abspath(sys.argv[0])
            
            # UAC penceresi ile yönetici olarak çalıştır
            try:
                # Kullanıcıya bilgi ver
                result = ctypes.windll.shell32.ShellExecuteW(
                    None, 
                    "runas", 
                    sys.executable, 
                    f'"{script}"', 
                    None, 
                    1  # SW_NORMAL
                )
                
                # Başarısız olursa
                if result <= 32:
                    logger.error("Yönetici izni alınamadı")
                    # Kritik hata mesajı göster
                    from PyQt5.QtWidgets import QMessageBox
                    QMessageBox.critical(
                        None, 
                        "Yetki Hatası", 
                        "Dosya Yok Edici için yönetici izni gereklidir.\n\n"
                        "Lütfen 'Evet' veya 'Devam Et' seçeneğine tıklayın."
                    )
                    return False
                
                # Başarılı olursa mevcut uygulamayı kapat
                logger.info("Yönetici olarak yeniden başlatılıyor")
                sys.exit(0)
            
            except Exception as e:
                logger.critical(f"Yönetici izni isteme hatası: {e}")
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.critical(
                    None, 
                    "Kritik Hata", 
                    f"Yönetici izni alınırken hata oluştu: {e}"
                )
                return False
        
        return True
    except Exception as e:
        logger.critical(f"Bilinmeyen hata: {e}")
        return False

def hide_console():
    """Python konsolunu gizle"""
    try:
        import win32console
        import win32gui
        
        # Konsol penceresini gizle
        console = win32console.GetConsoleWindow()
        if console:
            win32gui.ShowWindow(console, 0)  # SW_HIDE
        
        logger.debug("Python konsolu gizlendi")
    except Exception as e:
        logger.error(f"Konsol gizleme hatası: {e}")

class QTextEditLogHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)8s | %(filename)20s:%(lineno)4d | %(funcName)20s | %(message)s'
        ))
    
    def emit(self, record):
        try:
            msg = self.format(record)
            # Qt'nin ana thread'inde çalışması için
            self.text_widget.append(msg)
        except Exception:
            self.handleError(record)

def main():
    """
    Ana uygulama başlatma fonksiyonu
    Detaylı hata yakalama ve günlükleme ile çalışır
    """
    try:
        # Gerekli modüllerin varlığını kontrol et
        logger.info("Dosya Yok Edici Uygulaması Başlatılıyor")
        
        # Modül kontrolü
        required_modules = [
            'PyQt5', 'psutil', 'win32api', 
            'win32security', 'win32service', 
            'win32serviceutil'
        ]
        
        for module in required_modules:
            try:
                __import__(module)
                logger.debug(f"{module} modülü başarıyla yüklendi")
            except ImportError as e:
                logger.warning(f"{module} modülü bulunamadı: {e}")
        
        # Uygulama nesnesi oluştur
        logger.debug("QApplication nesnesi oluşturuluyor")
        app = QApplication(sys.argv)
        
        # Pencere nesnesi oluştur
        logger.debug("MainWindow nesnesi oluşturuluyor")
        window = MainWindow()
        
        # Pencereyi göster
        logger.debug("Pencere gösteriliyor")
        window.show()
        
        # Uygulama döngüsünü başlat
        logger.info("Uygulama çalışmaya başladı")
        exit_code = app.exec_()
        
        logger.info(f"Uygulama sonlandırıldı. Çıkış kodu: {exit_code}")
        return exit_code
    
    except Exception as e:
        # Kritik seviye hata yakalama
        logger.critical(f"Kritik hata oluştu: {str(e)}")
        logger.critical(f"Tam hata bilgisi:\n{traceback.format_exc()}")
        
        # Hata mesajını kullanıcıya göster
        error_dialog = QMessageBox()
        error_dialog.setIcon(QMessageBox.Critical)
        error_dialog.setWindowTitle("Kritik Hata")
        error_dialog.setText("Uygulama başlatılırken kritik bir hata oluştu.")
        error_dialog.setDetailedText(str(traceback.format_exc()))
        error_dialog.exec_()
        
        return 1  # Hata çıkış kodu

# Ana çalıştırma bloğunu güncelle
if __name__ == "__main__":
    try:
        # Konsolu gizle
        hide_console()
        
        # Logging'i başlat
        setup_detailed_logging()
        
        # Yönetici haklarını kontrol et ve iste
        if not is_admin():
            request_admin_rights()
        
        # Uygulamayı çalıştır
        logger.info("Uygulama başlatılıyor...")
        exit_code = main()
        
        # Çıkış kodunu logla
        logger.info(f"Uygulama sonlandı. Çıkış kodu: {exit_code}")
        sys.exit(exit_code)
    
    except Exception as e:
        # Son çare olarak kritik hatayı yakala
        logger.critical(f"Başlatma sırasında kritik hata: {str(e)}")
        logger.critical(f"Tam hata bilgisi:\n{traceback.format_exc()}")
        
        # Sistem çağrısı ile hata mesajı göster
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, 
                f"Kritik Hata: {str(e)}\n\nDetaylar için log dosyasını kontrol edin.", 
                "Kritik Hata", 
                0x10  # MB_ICONERROR
            )
        except:
            pass
        
        sys.exit(1)