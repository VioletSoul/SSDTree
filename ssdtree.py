import sys
import os
import weakref
import logging
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem,
    QHBoxLayout, QVBoxLayout, QWidget, QToolBar, QFileDialog,
    QSizePolicy, QComboBox, QLabel, QProgressBar
)
from PySide6.QtGui import QAction, QPainter, QColor
from PySide6.QtCharts import QChart, QChartView, QPieSeries
from PySide6.QtCore import (
    Qt, Signal, QObject, QThread, Slot,
    QDateTime, QLocale, QTimer, QMutex, QMutexLocker
)

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s][%(threadName)s][%(levelname)s] %(message)s'
)

def human_readable_size(size_bytes):
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    elif size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024 ** 2):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes} B"

class DirectoryLoader(QObject):
    items_loaded = Signal(object, list)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, path, parent_item, max_items=10000, batch_size=100):
        super().__init__()
        self.path = path
        self.parent_item_ref = weakref.ref(parent_item)
        self.max_items = max_items
        self.batch_size = batch_size
        self._is_interrupted = False
        self._mutex = QMutex()

    @Slot()
    def load_directory(self):
        logging.debug(f"Start loading directory: {self.path}")
        try:
            with QMutexLocker(self._mutex):
                if self._is_interrupted:
                    logging.debug("Interrupted before start")
                    return
            if not os.path.exists(self.path) or not os.path.isdir(self.path):
                self.error.emit(f"Path does not exist or is not a directory: {self.path}")
                return
            count = 0
            batch = []
            with os.scandir(self.path) as entries:
                for entry in entries:
                    with QMutexLocker(self._mutex):
                        if self._is_interrupted:
                            logging.debug("Interrupted during scan")
                            return
                    if count >= self.max_items:
                        break
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            size = 0
                            has_children = self._has_children(entry.path)
                        else:
                            size = entry.stat(follow_symlinks=False).st_size
                            has_children = False
                        ctime = QDateTime.fromSecsSinceEpoch(int(entry.stat(follow_symlinks=False).st_ctime))
                        batch.append((entry.name, size, entry.is_dir(follow_symlinks=False),
                                      entry.path, ctime, has_children))
                        count += 1
                    except Exception as e:
                        logging.warning(f"Exception while scanning {entry.path}: {e}")
                        continue
                    if len(batch) >= self.batch_size:
                        parent_item = self.parent_item_ref()
                        if parent_item is not None:
                            batch.sort(key=lambda x: (not x[2], x[0].lower()))
                            self.items_loaded.emit(parent_item, batch.copy())
                        batch.clear()
            if batch:
                parent_item = self.parent_item_ref()
                if parent_item is not None:
                    batch.sort(key=lambda x: (not x[2], x[0].lower()))
                    self.items_loaded.emit(parent_item, batch.copy())
            with QMutexLocker(self._mutex):
                if not self._is_interrupted:
                    parent_item = self.parent_item_ref()
                    if parent_item is not None:
                        self.finished.emit(parent_item)
            logging.debug(f"Finished loading directory: {self.path}")
        except Exception as e:
            logging.error(f"Error loading directory {self.path}: {str(e)}")
            self.error.emit(f"Error loading directory {self.path}: {str(e)}")

    def _has_children(self, path):
        try:
            with os.scandir(path) as entries:
                return any(True for _ in entries)
        except Exception as e:
            logging.warning(f"Error checking children for {path}: {e}")
            return False

    def interrupt(self):
        with QMutexLocker(self._mutex):
            self._is_interrupted = True
        logging.debug(f"DirectoryLoader interrupted for {self.path}")

class SortableTreeWidgetItem(QTreeWidgetItem):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_loading = False
        self._is_loaded = False
        self._full_path = None

    def __lt__(self, other):
        tree = self.treeWidget()
        if not tree:
            return super().__lt__(other)
        column = tree.sortColumn()
        sort_mode = getattr(tree, "_sort_mode", "name")
        if column == 0:
            if sort_mode == "name":
                return self.text(0).lower() < other.text(0).lower()
            elif sort_mode == "size":
                try:
                    s1 = float(self.text(1)) if self.text(1) else 0.0
                except ValueError:
                    s1 = 0.0
                try:
                    s2 = float(other.text(1)) if other.text(1) else 0.0
                except ValueError:
                    s2 = 0.0
                if s1 == s2:
                    return self.text(0).lower() < other.text(0).lower()
                return s1 > s2
            elif sort_mode == "date":
                dt1 = self.data(0, Qt.UserRole)
                dt2 = other.data(0, Qt.UserRole)
                if dt1 and dt2:
                    return dt1 < dt2
                else:
                    return self.text(0).lower() < other.text(0).lower()
            elif sort_mode == "type":
                is_dir1 = self.text(1) == ""
                is_dir2 = other.text(1) == ""
                if is_dir1 != is_dir2:
                    return is_dir1
                ext1 = os.path.splitext(self.text(0))[1].lower().lstrip('.') if not is_dir1 else ""
                ext2 = os.path.splitext(other.text(0))[1].lower().lstrip('.') if not is_dir2 else ""
                if ext1 == ext2:
                    return self.text(0).lower() < other.text(0).lower()
                return ext1 < ext2
        elif column == 1:
            try:
                s1 = float(self.text(1)) if self.text(1) else 0.0
            except ValueError:
                s1 = 0.0
            try:
                s2 = float(other.text(1)) if other.text(1) else 0.0
            except ValueError:
                s2 = 0.0
            return s1 < s2
        return super().__lt__(other)

    def set_full_path(self, path):
        self._full_path = path

    def get_full_path(self):
        return self._full_path

    def set_loading(self, loading):
        self._is_loading = loading

    def is_loading(self):
        return self._is_loading

    def set_loaded(self, loaded):
        self._is_loaded = loaded

    def is_loaded(self):
        return self._is_loaded

class FileTreeWidget(QTreeWidget):
    selection_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Имя", "Размер (КБ)"])
        header = self.header()
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
        self.itemSelectionChanged.connect(self.on_selection_changed)
        self.itemExpanded.connect(self.on_item_expanded)
        self.setMinimumWidth(300)
        self.setMaximumWidth(600)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._root_path = None
        self._sort_mode = "type"
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.AscendingOrder)
        self._active_threads = {}
        self._active_workers = {}
        self._mutex = QMutex()

    def set_sort_mode(self, mode):
        self._sort_mode = mode
        self.sortByColumn(0, Qt.AscendingOrder)

    def populate(self, path):
        self.clear()
        self._cleanup_threads()
        self._root_path = os.path.abspath(path)
        root_item = SortableTreeWidgetItem()
        root_item.setText(0, os.path.basename(path) or path)
        root_item.setText(1, "")
        root_item.set_full_path(path)
        self.addTopLevelItem(root_item)
        self._load_directory_async(path, root_item)
        root_item.setExpanded(True)

    def on_item_expanded(self, item):
        if not isinstance(item, SortableTreeWidgetItem):
            return
        path = item.get_full_path()
        if not path or not os.path.isdir(path):
            return
        if item.is_loaded() or item.is_loading():
            return
        self._load_directory_async(path, item)

    def _load_directory_async(self, path, parent_item):
        self._cleanup_thread(id(parent_item))
        if parent_item.is_loading():
            return
        parent_item.set_loading(True)
        thread = QThread(self)
        worker = DirectoryLoader(path, parent_item)
        worker.moveToThread(thread)
        item_id = id(parent_item)
        with QMutexLocker(self._mutex):
            self._active_threads[item_id] = thread
            self._active_workers[item_id] = worker
        thread.started.connect(worker.load_directory)
        worker.items_loaded.connect(self.on_items_loaded)
        worker.finished.connect(self.on_loading_finished)
        worker.error.connect(self.on_loading_error)
        worker.finished.connect(lambda: self._cleanup_thread(item_id))
        thread.finished.connect(thread.deleteLater)
        thread.start()
        logging.debug(f"Started DirectoryLoader thread for {path}")

    @Slot(object, list)
    def on_items_loaded(self, parent_item, items_data):
        if not isinstance(parent_item, SortableTreeWidgetItem):
            return
        if parent_item.treeWidget() is None:
            return
        for name, size, is_dir, full_path, ctime, has_children in items_data:
            item = SortableTreeWidgetItem(parent_item)
            item.setText(0, name)
            item.set_full_path(full_path)
            if ctime:
                item.setData(0, Qt.UserRole, ctime)
            if is_dir:
                item.setText(1, "")
                if has_children:
                    dummy = SortableTreeWidgetItem(item)
                    dummy.setText(0, "Загрузка...")
                    dummy.setText(1, "")
            else:
                size_kb = size / 1024 if size > 0 else 0
                item.setText(1, f"{size_kb:.2f}" if size_kb > 0 else "0.00")
        parent_item.sortChildren(0, Qt.AscendingOrder)

    @Slot(object)
    def on_loading_finished(self, parent_item):
        if isinstance(parent_item, SortableTreeWidgetItem):
            parent_item.set_loading(False)
            parent_item.set_loaded(True)
        logging.debug(f"Finished loading for {getattr(parent_item, '_full_path', None)}")

    @Slot(str)
    def on_loading_error(self, error_msg):
        logging.error(error_msg)

    def _cleanup_thread(self, item_id):
        with QMutexLocker(self._mutex):
            thread = self._active_threads.pop(item_id, None)
            worker = self._active_workers.pop(item_id, None)
        if worker:
            worker.interrupt()
            try:
                worker.items_loaded.disconnect()
            except Exception:
                pass
            try:
                worker.finished.disconnect()
            except Exception:
                pass
            try:
                worker.error.disconnect()
            except Exception:
                pass
            worker.deleteLater()
        if thread:
            thread.quit()
            thread.wait()
            thread.deleteLater()
        logging.debug(f"Cleaned up thread and worker for item_id={item_id}")

    def _cleanup_threads(self):
        with QMutexLocker(self._mutex):
            item_ids = list(self._active_threads.keys())
        for item_id in item_ids:
            self._cleanup_thread(item_id)

    def on_selection_changed(self):
        selected = self.selectedItems()
        if selected:
            item = selected[0]
            if isinstance(item, SortableTreeWidgetItem):
                path = item.get_full_path()
                if path:
                    self.selection_changed.emit(path)

    def closeEvent(self, event):
        self._cleanup_threads()
        super().closeEvent(event)

class FolderSizeWorker(QObject):
    finished = Signal(dict)
    error = Signal(str)
    progress = Signal(int)

    def __init__(self, path):
        super().__init__()
        self.path = path
        self._is_interrupted = False
        self._mutex = QMutex()

    @Slot()
    def process(self):
        logging.debug(f"Start calculating sizes in: {self.path}")
        try:
            data = {}
            entries = list(os.scandir(self.path))
            total = len(entries)
            for idx, entry in enumerate(entries):
                with QMutexLocker(self._mutex):
                    if self._is_interrupted:
                        logging.debug("Interrupted during size calculation")
                        return
                try:
                    if entry.is_dir(follow_symlinks=False):
                        size = self.get_folder_size(entry.path)
                    else:
                        size = entry.stat(follow_symlinks=False).st_size
                    if size > 0:
                        data[entry.name] = size
                    self.progress.emit(int((idx+1)/total*100))
                except Exception as e:
                    logging.warning(f"Error processing {entry.path}: {e}")
                    continue
            self.finished.emit(data)
            logging.debug(f"Finished calculating sizes in: {self.path}")
        except Exception as e:
            logging.error(f"Error in FolderSizeWorker: {e}")
            self.error.emit(str(e))

    def get_folder_size(self, folder):
        total = 0
        try:
            for root, dirs, files in os.walk(folder):
                with QMutexLocker(self._mutex):
                    if self._is_interrupted:
                        return 0
                for f in files:
                    try:
                        fp = os.path.join(root, f)
                        total += os.path.getsize(fp)
                    except Exception:
                        pass
        except Exception:
            pass
        return total

    def interrupt(self):
        with QMutexLocker(self._mutex):
            self._is_interrupted = True
        logging.debug(f"FolderSizeWorker interrupted for {self.path}")

class PieChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.series = QPieSeries()
        self.chart = QChart()
        self.chart.addSeries(self.series)
        self.chart.setTitle("")
        self.chart.legend().setAlignment(Qt.AlignRight)
        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.chart_view)
        self.colors = [
            QColor("#e6194b"), QColor("#3cb44b"), QColor("#ffe119"),
            QColor("#4363d8"), QColor("#f58231"), QColor("#911eb4"),
            QColor("#46f0f0"), QColor("#f032e6"), QColor("#bcf60c"),
            QColor("#fabebe"), QColor("#008080"), QColor("#e6beff"),
            QColor("#9a6324"), QColor("#fffac8"), QColor("#800000"),
            QColor("#aaffc3"), QColor("#808000"), QColor("#ffd8b1"),
            QColor("#000075"), QColor("#808080"), QColor("#ff4500"),
            QColor("#2e8b57"), QColor("#1e90ff"), QColor("#ff69b4"),
            QColor("#8a2be2"), QColor("#00ced1"), QColor("#ff8c00"),
            QColor("#7fff00"), QColor("#dc143c"), QColor("#00fa9a"),
        ]

    def update_data(self, data, folder_name, empty_folder_title):
        self.series.clear()
        if not data:
            self.chart.setTitle(empty_folder_title)
            return
        self.chart.setTitle(folder_name)
        data_sorted = sorted(data.items(), key=lambda x: x[1], reverse=True)
        total_size = sum(size for _, size in data_sorted)
        for i, (name, size) in enumerate(data_sorted):
            slice = self.series.append(name, size)
            slice.setBrush(self.colors[i % len(self.colors)])
            percent = size / total_size * 100
            if percent > 1.4:
                slice.setLabelVisible(True)
                slice.setLabel(f"{name}\n{percent:.1f}%")
            else:
                slice.setLabelVisible(False)
        legend = self.chart.legend()
        for marker in legend.markers():
            label = marker.label()
            name = label.split('\n')[0]
            size_bytes = data.get(name, 0)
            label_text = f"{name} — {human_readable_size(size_bytes)}"
            marker.setLabel(label_text)
        self.chart.legend().setVisible(True)

    def clear_chart(self):
        if self.series is not None:
            try:
                self.chart.removeSeries(self.series)
            except RuntimeError:
                pass
            else:
                self.series.deleteLater()
            self.series = None
        self.chart.setTitle("")

class InfoOverlay(QWidget):
    def __init__(self, parent, properties):
        super().__init__(parent)
        self.properties = properties
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(parent.rect())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(Qt.black)
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        margin = 10
        line_height = painter.fontMetrics().height() + 4
        y = margin
        for key, value in self.properties:
            painter.drawText(margin, y + line_height, f"{key}: {value}")
            y += line_height
        painter.end()

    def resizeEvent(self, event):
        self.setGeometry(self.parent().rect())

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # --- Локализация ---
        self.languages = ['ru', 'en']
        self.lang = 'ru'
        self.texts = {
            'ru': {
                'title': "Дерево папок и диаграммы QtCharts (Оптимизированная версия)",
                'open_folder': "Открыть папку",
                'sort_label': "Сортировка:",
                'sort_modes': ["По имени", "По размеру", "По дате создания", "По типу"],
                'empty_folder': "Папка пуста или нет доступа",
                'file_props': "Свойства файла: {}",
                'size_col': "Размер (КБ)",
                'name_col': "Имя",
                'props_path': "Путь",
                'props_size': "Размер",
                'props_last_mod': "Последнее изменение",
                'props_last_acc': "Последний доступ",
                'props_created': "Время создания",
                'props_rights': "Права доступа",
                'props_is_dir': "Является директорией",
                'props_is_file': "Является файлом",
                'err_size': "Ошибка при подсчёте размеров: {}",
                'props_yes': "Да",
                'props_no': "Нет",
                'select_folder': "Выберите папку",
            },
            'en': {
                'title': "Folder Tree & QtCharts Diagrams (Optimized)",
                'open_folder': "Open Folder",
                'sort_label': "Sort by:",
                'sort_modes': ["By Name", "By Size", "By Creation Date", "By Type"],
                'empty_folder': "Folder is empty or inaccessible",
                'file_props': "File properties: {}",
                'size_col': "Size (KB)",
                'name_col': "Name",
                'props_path': "Path",
                'props_size': "Size",
                'props_last_mod': "Last modified",
                'props_last_acc': "Last accessed",
                'props_created': "Created",
                'props_rights': "Permissions",
                'props_is_dir': "Is directory",
                'props_is_file': "Is file",
                'err_size': "Error calculating sizes: {}",
                'props_yes': "Yes",
                'props_no': "No",
                'select_folder': "Select Folder",
            }
        }

        self.setWindowTitle(self.texts[self.lang]['title'])
        self.resize(1000, 600)
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(5)

        # --- Языковой переключатель ---
        self.combo_lang = QComboBox()
        self.combo_lang.addItems(['Русский', 'English'])
        self.combo_lang.setMaximumWidth(120)
        self.combo_lang.currentIndexChanged.connect(self.switch_language)
        left_layout.addWidget(self.combo_lang)

        self.label_sort = QLabel(self.texts[self.lang]['sort_label'])
        left_layout.addWidget(self.label_sort)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(self.texts[self.lang]['sort_modes'])
        self.sort_combo.currentIndexChanged.connect(self.on_sort_mode_changed)
        left_layout.addWidget(self.sort_combo)
        self.tree = FileTreeWidget(self)
        left_layout.addWidget(self.tree)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        left_layout.addWidget(self.progress_bar)
        left_widget.setMaximumWidth(350)
        main_layout.addWidget(left_widget)
        self.chart_widget = PieChartWidget(self)
        main_layout.addWidget(self.chart_widget, stretch=1)
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        self.open_action = QAction(self.texts[self.lang]['open_folder'], self)
        self.open_action.triggered.connect(self.open_folder)
        toolbar.addAction(self.open_action)
        self.tree.selection_changed.connect(self.on_tree_selection_changed)
        self.worker = None
        self.thread = None
        self.current_worker_id = 0
        self.showing_file_info = False
        self.info_overlay = None
        self.sort_combo.setCurrentIndex(3)
        self.tree.set_sort_mode("type")

    def switch_language(self, idx):
        self.lang = self.languages[idx]
        self.update_ui_texts()

    def update_ui_texts(self):
        t = self.texts[self.lang]
        self.setWindowTitle(t['title'])
        self.open_action.setText(t['open_folder'])
        self.label_sort.setText(t['sort_label'])
        self.sort_combo.blockSignals(True)
        self.sort_combo.clear()
        self.sort_combo.addItems(t['sort_modes'])
        self.sort_combo.setCurrentIndex(3)
        self.sort_combo.blockSignals(False)
        self.tree.setHeaderLabels([t['name_col'], t['size_col']])
        if self.chart_widget.series is not None and self.showing_file_info is False:
            self.chart_widget.chart.setTitle("")
        if self.info_overlay is not None:
            self.remove_info_overlay()

    def on_sort_mode_changed(self, index):
        modes = ["name", "size", "date", "type"]
        mode = modes[index]
        self.tree.set_sort_mode(mode)

    def open_folder(self):
        t = self.texts[self.lang]
        folder = QFileDialog.getExistingDirectory(self, t['select_folder'])
        if folder:
            self._cancel_previous_operations()
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            self.tree.populate(folder)
            self.showing_file_info = False
            self.remove_info_overlay()
            self.chart_widget.clear_chart()
            self.create_new_series()
            QTimer.singleShot(1000, lambda: self.progress_bar.setVisible(False))

    def _cancel_previous_operations(self):
        if self.worker and self.thread:
            self.worker.interrupt()
            self.thread.quit()
            self.thread.wait(1000)
            self.worker = None
            self.thread = None
        self.tree._cleanup_threads()

    def on_tree_selection_changed(self, path):
        if os.path.isdir(path):
            if self.showing_file_info:
                self.showing_file_info = False
                self.remove_info_overlay()
                self.create_new_series()
            self.start_folder_size_worker(path)
        else:
            self.showing_file_info = True
            self.remove_info_overlay()
            self.show_file_properties(path)

    def show_file_properties(self, path):
        t = self.texts[self.lang]
        try:
            stat = os.stat(path)
        except Exception:
            self.chart_widget.clear_chart()
            return
        locale = QLocale.system()
        mtime = QDateTime.fromSecsSinceEpoch(int(stat.st_mtime))
        atime = QDateTime.fromSecsSinceEpoch(int(stat.st_atime))
        ctime = QDateTime.fromSecsSinceEpoch(int(stat.st_ctime))
        props = [
            (t['props_path'], path),
            (t['props_size'], human_readable_size(stat.st_size)),
            (t['props_last_mod'], locale.toString(mtime, QLocale.LongFormat)),
            (t['props_last_acc'], locale.toString(atime, QLocale.LongFormat)),
            (t['props_created'], locale.toString(ctime, QLocale.LongFormat)),
            (t['props_rights'], oct(stat.st_mode)[-3:]),
            (t['props_is_dir'], t['props_yes'] if os.path.isdir(path) else t['props_no']),
            (t['props_is_file'], t['props_yes'] if os.path.isfile(path) else t['props_no']),
        ]
        chart = self.chart_widget.chart
        chart.removeAllSeries()
        chart.setTitle(t['file_props'].format(os.path.basename(path)))
        self.info_overlay = InfoOverlay(self.chart_widget.chart_view.viewport(), props)
        self.info_overlay.show()

    def remove_info_overlay(self):
        if self.info_overlay is not None:
            self.info_overlay.hide()
            self.info_overlay.setParent(None)
            self.info_overlay.deleteLater()
            self.info_overlay = None

    def create_new_series(self):
        if self.chart_widget.series is not None:
            try:
                self.chart_widget.chart.removeSeries(self.chart_widget.series)
                self.chart_widget.series.deleteLater()
            except RuntimeError:
                pass
        self.chart_widget.series = QPieSeries()
        self.chart_widget.chart.addSeries(self.chart_widget.series)
        self.chart_widget.chart.legend().setVisible(True)

    def start_folder_size_worker(self, path):
        self.current_worker_id += 1
        worker_id = self.current_worker_id
        self._cancel_previous_operations()
        self.thread = QThread(self)
        self.worker = FolderSizeWorker(path)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.process)
        self.worker.finished.connect(lambda data: self.on_worker_finished(data, worker_id))
        self.worker.error.connect(self.on_worker_error)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.clear_thread_worker_refs)
        self.thread.start()
        logging.debug(f"Started FolderSizeWorker thread for {path}")

    def on_worker_finished(self, data, worker_id):
        if worker_id != self.current_worker_id:
            return
        self.progress_bar.setVisible(False)
        if self.worker and self.worker.path:
            folder_name = os.path.basename(self.worker.path)
            self.create_new_series()
            self.chart_widget.update_data(
                data,
                folder_name,
                self.texts[self.lang]['empty_folder']
            )
        self.clear_thread_worker_refs()

    def on_worker_error(self, error_msg):
        t = self.texts[self.lang]
        self.chart_widget.chart.setTitle(t['err_size'].format(error_msg))
        self.progress_bar.setVisible(False)
        logging.error(f"FolderSizeWorker error: {error_msg}")

    def clear_thread_worker_refs(self):
        self.thread = None
        self.worker = None

    def closeEvent(self, event):
        self._cancel_previous_operations()
        self.tree._cleanup_threads()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
