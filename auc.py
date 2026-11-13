import sys
import json
import os
import re
import time
import webbrowser # Для открытия ссылок в браузере
import pyautogui
import pyperclip
import keyboard
import pygetwindow as gw
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLineEdit, 
                             QCompleter, QListWidget, QPushButton, QHBoxLayout, 
                             QToolTip, QMessageBox, QRubberBand, QAbstractItemView, 
                             QLabel, QInputDialog, QCheckBox)
from PyQt5.QtCore import Qt, QTimer, QRect, QPoint, QSize, pyqtSignal
from PyQt5.QtGui import QCursor, QColor, QPainter, QPixmap

# ================= НАСТРОЙКИ =================
CONFIG_FILE = 'config.json'
WATCHLIST_FILE = 'watchlist.json'   
ITEMS_DB_FILE = 'items.json'        
SCREENSHOTS_DIR = 'screenshots'     
GAME_WINDOW_TITLE = "SO official game client" 
# ============================================

if not os.path.exists(SCREENSHOTS_DIR):
    os.makedirs(SCREENSHOTS_DIR)

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name)

# --- КЛАСС ДЛЯ ВЫДЕЛЕНИЯ ОБЛАСТИ ЭКРАНА (КАЛИБРОВКА) ---
class RegionSelector(QWidget):
    regionSelected = pyqtSignal(tuple)
    
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowState(Qt.WindowFullScreen)
        self.setCursor(Qt.CrossCursor)
        
        self.rubberBand = QRubberBand(QRubberBand.Rectangle, self)
        self.rubberBand.setStyleSheet("background-color: rgba(0, 120, 215, 80); border: 2px solid #0078D7;")
        self.origin = QPoint()
        self.region = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.origin = event.pos()
            self.rubberBand.setGeometry(QRect(self.origin, QSize()))
            self.rubberBand.show()

    def mouseMoveEvent(self, event):
        if self.rubberBand.isVisible():
            self.rubberBand.setGeometry(QRect(self.origin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            rect = self.rubberBand.geometry()
            if rect.width() > 5 and rect.height() > 5:
                self.region = (rect.x(), rect.y(), rect.width(), rect.height())
                self.regionSelected.emit(self.region)
            self.close()

    def closeEvent(self, event):
        if self.region is None:
            self.regionSelected.emit(None)
        event.accept()

# --- ВСПЛЫВАЮЩЕЕ ОКНО ДЛЯ КАРТИНКИ ---
class ImagePreview(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.label = QLabel(self)
        self.label.setStyleSheet("background-color: #1e1e1e; border: 2px solid #0078D7; padding: 2px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        self.hide()

    def show_image(self, pixmap, main_window_geo):
        self.label.setPixmap(pixmap)
        self.resize(pixmap.width(), pixmap.height())
        
        x = main_window_geo.x() - self.width() - 10
        y = main_window_geo.y()
        
        if x < 0:
            x = main_window_geo.x() + main_window_geo.width() + 10
            
        screen_geo = QApplication.primaryScreen().availableGeometry()
        if y + self.height() > screen_geo.bottom():
            y = screen_geo.bottom() - self.height() - 10
        if y < 0:
            y = 10
            
        self.move(x, y)
        self.show()

# --- ГЛАВНОЕ ОКНО ПРОГРАММЫ ---
class OverlayApp(QWidget):
    def __init__(self):
        super().__init__()
        self.screenshots = {} 
        self.config = self.load_config()
        self.preview_window = ImagePreview() 
        self.all_items = [] 
        self.initUI()
        self.load_items()
        self.load_watchlist()

    def initUI(self):
        self.setWindowTitle('Помощник торговца - Stay Out')
        self.setGeometry(100, 100, 480, 650) # Чуть шире для новых кнопок
        self.setWindowOpacity(0.95)
        
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: white; font-family: Arial; font-size: 13px;}
            QLineEdit { background-color: #333; border: 1px solid #555; padding: 5px; border-radius: 3px; }
            QListWidget { background-color: #252525; border: 1px solid #555; border-radius: 3px; }
            QListWidget::item { padding: 5px; }
            QListWidget::item:hover { background-color: #444; }
            QPushButton { background-color: #005A9E; border: none; padding: 6px; font-weight: bold; border-radius: 3px; }
            QPushButton:hover { background-color: #0078D7; }
            QPushButton#btn_del { background-color: #A30000; }
            QPushButton#btn_del:hover { background-color: #D00000; }
            QPushButton#btn_calib { background-color: #555; }
            QPushButton#btn_calib:hover { background-color: #777; }
            QPushButton#btn_edit { background-color: #8B5A00; }
            QPushButton#btn_edit:hover { background-color: #B8860B; }
            QPushButton#btn_wiki { background-color: #006400; }
            QPushButton#btn_wiki:hover { background-color: #008000; }
            QCheckBox { color: #aaa; font-weight: bold; }
        """)

        layout = QVBoxLayout()

        search_layout = QHBoxLayout()
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Введите название (можно любое)...")
        self.search_input.returnPressed.connect(self.add_to_watchlist)
        search_layout.addWidget(self.search_input)

        add_btn = QPushButton("Добавить", self)
        add_btn.clicked.connect(self.add_to_watchlist)
        search_layout.addWidget(add_btn)
        layout.addLayout(search_layout)

        self.chk_topmost = QCheckBox("Поверх всех окон (Overlay Mode)")
        self.chk_topmost.setChecked(True)
        self.chk_topmost.stateChanged.connect(self.toggle_topmost)
        layout.addWidget(self.chk_topmost)

        self.watch_list = QListWidget(self)
        self.watch_list.itemDoubleClicked.connect(self.take_screenshot)
        self.watch_list.setMouseTracking(True)
        self.watch_list.itemEntered.connect(self.show_preview)
        self.watch_list.leaveEvent = self.hide_preview 
        self.watch_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.watch_list)

        # Блок кнопок
        control_layout = QHBoxLayout()
        
        del_btn = QPushButton("Удалить", self)
        del_btn.setObjectName("btn_del")
        del_btn.clicked.connect(self.delete_selected)
        control_layout.addWidget(del_btn)

        edit_btn = QPushButton("Переименовать", self)
        edit_btn.setObjectName("btn_edit")
        edit_btn.clicked.connect(self.rename_item)
        control_layout.addWidget(edit_btn)

        # Новая кнопка Wiki
        wiki_btn = QPushButton("Открыть Wiki", self)
        wiki_btn.setObjectName("btn_wiki")
        wiki_btn.clicked.connect(self.open_wiki)
        control_layout.addWidget(wiki_btn)
        
        layout.addLayout(control_layout)

        # Кнопка калибровки в самом низу
        calib_btn = QPushButton("Калибровка", self)
        calib_btn.setObjectName("btn_calib")
        calib_btn.clicked.connect(self.run_calibration)
        layout.addWidget(calib_btn)

        self.setLayout(layout)

        QTimer.singleShot(500, self.check_first_run)

    def toggle_topmost(self, state):
        geo = self.geometry()
        if state == Qt.Checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.setGeometry(geo)
        self.show()

    # === ОТКРЫТИЕ WIKI ===
    def open_wiki(self):
        selected = self.watch_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Внимание", "Сначала выделите предмет в списке!")
            return
        
        # Берем первый выделенный предмет
        item = selected[0]
        item_name = item.text().split("   [")[0].strip()
        
        # Формируем URL (пробелы меняем на подчеркивания)
        safe_url_name = item_name.replace(" ", "_")
        wiki_url = f"https://so-wiki.ru/wiki/{safe_url_name}"
        
        print(f"[WIKI] Открываем: {wiki_url}")
        webbrowser.open(wiki_url)
    # =====================

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"search_x": 0, "search_y": 0, "price_region": [0, 0, 0, 0]}

    def save_config(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f)

    def check_first_run(self):
        if self.config["search_x"] == 0 or self.config["price_region"][2] == 0:
            self.run_calibration()

    def run_calibration(self):
        QMessageBox.information(self, "Калибровка 1/2", 
            "Наведите курсор мыши на ПОЛЕ ВВОДА НАЗВАНИЯ в игре.\n\n"
            "После закрытия этого окна у вас будет 5 секунд, чтобы навести мышь на поле.")
        self.hide()
        time.sleep(5)
        mx, my = pyautogui.position()
        self.config["search_x"] = mx
        self.config["search_y"] = my

        QMessageBox.information(self, "Калибровка 2/2", 
            "Сейчас экран станет темным.\n"
            "Зажмите ЛЕВУЮ КНОПКУ МЫШИ и выделите область так, чтобы в кадр попадали И НАЗВАНИЯ, И ЦЕНЫ первых 3 строк.")
        
        self.region_selector = RegionSelector()
        self.region_selector.regionSelected.connect(self.on_region_selected)
        self.region_selector.show()

    def on_region_selected(self, region):
        if region:
            self.config["price_region"] = list(region)
            self.save_config()
            QMessageBox.information(self, "Готово", "Калибровка сохранена!")
        self.show()
        self.activateWindow()

    def load_items(self):
        try:
            with open(ITEMS_DB_FILE, 'r', encoding='utf-8') as f:
                self.all_items = json.load(f)
        except FileNotFoundError:
            self.all_items = ["Свинец", "Патрон 7.62x25 ТТ", "АК-103"]
            self.save_items_db()

        self.update_completer()

    def save_items_db(self):
        try:
            with open(ITEMS_DB_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.all_items, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[ОШИБКА] Не удалось сохранить items.json: {e}")

    def update_completer(self):
        self.completer = QCompleter(self.all_items, self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.search_input.setCompleter(self.completer)

    def load_watchlist(self):
        if not os.path.exists(WATCHLIST_FILE):
            return
            
        try:
            with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
                items = json.load(f)
                
            for item_name in items:
                safe_name = sanitize_filename(item_name)
                img_path = os.path.join(SCREENSHOTS_DIR, f"{safe_name}.png")
                
                if os.path.exists(img_path):
                    self.screenshots[item_name] = QPixmap(img_path)
                    self.watch_list.addItem(f"{item_name}   [Скриншот готов]")
                else:
                    self.watch_list.addItem(item_name)
        except Exception as e:
            print(f"Ошибка загрузки списка: {e}")

    def save_watchlist(self):
        items = []
        for i in range(self.watch_list.count()):
            item_text = self.watch_list.item(i).text()
            item_name = item_text.split("   [")[0]
            items.append(item_name)
            
        with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=4)

    def add_to_watchlist(self):
        text = self.search_input.text().strip()
        if not text: return
        
        items = [self.watch_list.item(i).text().split("   [")[0] for i in range(self.watch_list.count())]
        if text not in items:
            self.watch_list.addItem(text)
            self.save_watchlist()
            
        if text not in self.all_items:
            self.all_items.append(text)
            self.all_items.sort() 
            self.save_items_db()
            self.update_completer()
            print(f"[БАЗА] Новый предмет '{text}' успешно добавлен в items.json")
            
        self.search_input.clear()

    def delete_selected(self):
        selected_items = self.watch_list.selectedItems()
        if not selected_items:
            return

        for item in selected_items:
            item_name = item.text().split("   [")[0]
            
            if item_name in self.screenshots:
                del self.screenshots[item_name]
                
            safe_name = sanitize_filename(item_name)
            img_path = os.path.join(SCREENSHOTS_DIR, f"{safe_name}.png")
            
            if os.path.exists(img_path):
                try:
                    os.remove(img_path)
                except Exception:
                    pass

        for item in selected_items:
            self.watch_list.takeItem(self.watch_list.row(item))
        
        self.save_watchlist()

    def rename_item(self):
        selected = self.watch_list.selectedItems()
        if not selected: return
        if len(selected) > 1:
            QMessageBox.warning(self, "Внимание", "Выберите только один предмет для переименования.")
            return
            
        item = selected[0]
        old_name = item.text().split("   [")[0]
        
        new_name, ok = QInputDialog.getText(self, "Переименовать предмет", 
                                            "Введите новое название:", 
                                            QLineEdit.Normal, old_name)
        
        if ok and new_name and new_name.strip() != "" and new_name != old_name:
            new_name = new_name.strip()
            
            status_suffix = ""
            if old_name in self.screenshots:
                self.screenshots[new_name] = self.screenshots.pop(old_name)
                
                old_safe = sanitize_filename(old_name)
                new_safe = sanitize_filename(new_name)
                old_path = os.path.join(SCREENSHOTS_DIR, f"{old_safe}.png")
                new_path = os.path.join(SCREENSHOTS_DIR, f"{new_safe}.png")
                
                if os.path.exists(old_path):
                    try:
                        os.rename(old_path, new_path)
                    except Exception:
                        pass
                        
                status_suffix = "   [Скриншот готов]"
                
            item.setText(f"{new_name}{status_suffix}")
            self.save_watchlist()

    def show_preview(self, item):
        item_name = item.text().split("   [")[0]
        if item_name in self.screenshots:
            self.preview_window.show_image(self.screenshots[item_name], self.geometry())

    def hide_preview(self, event):
        self.preview_window.hide()
        super().leaveEvent(event)

    def take_screenshot(self, item):
        item_name = item.text().split("   [")[0]
        
        if self.config["search_x"] == 0:
            QMessageBox.warning(self, "Ошибка", "Сначала выполните калибровку!")
            return

        self.hide()
        self.preview_window.hide()
        time.sleep(0.3) 

        try:
            windows = gw.getWindowsWithTitle(GAME_WINDOW_TITLE)
            if not windows:
                self.show()
                return

            game_window = windows[0]
            if game_window.isMinimized:
                game_window.restore()
            game_window.activate()
            time.sleep(0.8)

            pyautogui.click(self.config["search_x"], self.config["search_y"])
            time.sleep(0.4)
            
            pyautogui.press('backspace', presses=40, interval=0.01)
            pyautogui.press('delete', presses=40, interval=0.01)
            time.sleep(0.2)

            pyperclip.copy(item_name)
            time.sleep(0.2)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.3)
            keyboard.write(item_name, delay=0.02)
            time.sleep(0.3)

            pyautogui.press('enter')
            time.sleep(1.5)
            
            region = tuple(self.config["price_region"])
            safe_name = sanitize_filename(item_name)
            img_path = os.path.join(SCREENSHOTS_DIR, f"{safe_name}.png")
            
            pil_image = pyautogui.screenshot(region=region)
            pil_image.save(img_path)
            
            self.screenshots[item_name] = QPixmap(img_path)
            item.setText(f"{item_name}   [Скриншот готов]")

        except Exception as e:
            print(f"[КРИТИЧЕСКАЯ ОШИБКА] {e}")
            item.setText(f"{item_name}   [Ошибка]")
        finally:
            self.show()
            self.activateWindow()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    overlay = OverlayApp()
    overlay.show()
    sys.exit(app.exec_())