import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem,
    QHBoxLayout, QVBoxLayout, QWidget, QToolBar, QFileDialog,
    QSizePolicy, QComboBox, QLabel
)
from PySide6.QtGui import QAction, QPainter, QColor
from PySide6.QtCharts import QChart, QChartView, QPieSeries
from PySide6.QtCore import Qt, Signal, QObject, QThread, Slot, QDateTime


def human_readable_size(size_bytes):
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.2f} ГБ"
    elif size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024 ** 2):.2f} МБ"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} КБ"
    else:
        return f"{size_bytes} Б"


class SortableTreeWidgetItem(QTreeWidgetItem):
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
                # Сортируем по расширению файла (без точки), папки идут первыми
                is_dir1 = self.text(1) == ""
                is_dir2 = other.text(1) == ""
                if is_dir1 != is_dir2:
                    return is_dir1  # папки выше файлов
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


class FileTreeWidget(QTreeWidget):
    selection_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Имя", "Размер (КБ)"])
        header = self.header()
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
        self.itemSelectionChanged.connect(self.on_selection_changed)

        self.setMinimumWidth(300)
        self.setMaximumWidth(600)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self._root_path = None
        self._sort_mode = "name"
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.AscendingOrder)

    def set_sort_mode(self, mode):
        self._sort_mode = mode
        self.sortByColumn(0, Qt.AscendingOrder)

    def populate(self, path):
        self.clear()
        self._root_path = os.path.abspath(path)
        self._add_items(self._root_path, self.invisibleRootItem())

    def _add_items(self, path, parent_item):
        try:
            entries = list(os.scandir(path))
        except PermissionError:
            return
        except Exception as e:
            print(f"Ошибка при сканировании {path}: {e}")
            return

        items = []
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    size = 0
                else:
                    size = entry.stat(follow_symlinks=False).st_size
                ctime = QDateTime.fromSecsSinceEpoch(int(entry.stat(follow_symlinks=False).st_ctime))
                items.append((entry.name, size, entry.is_dir(follow_symlinks=False), entry, ctime))
            except Exception:
                items.append((entry.name, 0, entry.is_dir(follow_symlinks=False), entry, None))

        items.sort(key=lambda x: x[0].lower())

        for name, size, is_dir, entry, ctime in items:
            item = SortableTreeWidgetItem(parent_item)
            item.setText(0, name)
            if ctime:
                item.setData(0, Qt.UserRole, ctime)
            if is_dir:
                item.setText(1, "")
                self._add_items(entry.path, item)
            else:
                size_kb = size / 1024
                item.setText(1, f"{size_kb:.2f}")

    def on_selection_changed(self):
        selected = self.selectedItems()
        if selected:
            item = selected[0]
            path = self.get_full_path(item)
            if path:
                self.selection_changed.emit(path)

    def get_full_path(self, item):
        parts = []
        current = item
        while current:
            parts.insert(0, current.text(0))
            current = current.parent()
        if self._root_path:
            full_path = os.path.join(self._root_path, *parts)
            return full_path
        else:
            return os.path.join(*parts)


class FolderSizeWorker(QObject):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, path):
        super().__init__()
        self.path = path

    @Slot()
    def process(self):
        try:
            data = {}
            with os.scandir(self.path) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            size = self.get_folder_size(entry.path)
                        else:
                            size = entry.stat(follow_symlinks=False).st_size
                        if size > 0:
                            data[entry.name] = size
                    except Exception:
                        continue
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))

    def get_folder_size(self, folder):
        total = 0
        for root, dirs, files in os.walk(folder):
            for f in files:
                try:
                    fp = os.path.join(root, f)
                    total += os.path.getsize(fp)
                except Exception:
                    pass
        return total


class PieChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.series = QPieSeries()
        self.chart = QChart()
        self.chart.addSeries(self.series)
        self.chart.setTitle("Размеры файлов и папок")
        self.chart.legend().setAlignment(Qt.AlignRight)

        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.Antialiasing)

        layout = QHBoxLayout(self)
        layout.addWidget(self.chart_view)

        self.colors = [
            QColor("#e6194b"), QColor("#3cb44b"), QColor("#ffe119"),
            QColor("#4363d8"), QColor("#f58231"), QColor("#911eb4"),
            QColor("#46f0f0"), QColor("#f032e6"), QColor("#bcf60c"),
            QColor("#fabebe"), QColor("#008080"), QColor("#e6beff"),
            QColor("#9a6324"), QColor("#fffac8"), QColor("#800000"),
            QColor("#aaffc3"), QColor("#808000"), QColor("#ffd8b1"),
            QColor("#000075"), QColor("#808080"),
        ]

    def update_data(self, data, folder_name):
        self.series.clear()
        if not data:
            self.chart.setTitle("Папка пуста или нет доступа")
            return

        self.chart.setTitle(f"Размеры в папке: {folder_name}")

        data_sorted = sorted(data.items(), key=lambda x: x[1], reverse=True)
        total_size = sum(size for _, size in data_sorted)

        for i, (name, size) in enumerate(data_sorted):
            slice = self.series.append(name, size)
            slice.setBrush(self.colors[i % len(self.colors)])
            percent = size / total_size * 100
            if percent > 2:
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
        self.series.clear()
        self.chart.setTitle("")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Дерево папок и диаграммы QtCharts")
        self.resize(1000, 600)

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(5)

        label = QLabel("Сортировка:")
        left_layout.addWidget(label)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["По имени", "По размеру", "По дате создания", "По типу"])
        self.sort_combo.currentIndexChanged.connect(self.on_sort_mode_changed)
        left_layout.addWidget(self.sort_combo)

        self.tree = FileTreeWidget(self)
        left_layout.addWidget(self.tree)

        left_widget.setMaximumWidth(350)

        main_layout.addWidget(left_widget)

        self.chart_widget = PieChartWidget(self)
        main_layout.addWidget(self.chart_widget, stretch=1)

        toolbar = QToolBar()
        self.addToolBar(toolbar)
        open_action = QAction("Открыть папку", self)
        open_action.triggered.connect(self.open_folder)
        toolbar.addAction(open_action)

        self.tree.selection_changed.connect(self.update_chart)

        self.thread = None
        self.worker = None

    def on_sort_mode_changed(self, index):
        modes = ["name", "size", "date", "type"]
        mode = modes[index]
        self.tree.set_sort_mode(mode)

    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку")
        if folder:
            self.tree.populate(folder)
            self.start_folder_size_worker(folder)

    def update_chart(self, path):
        if os.path.isdir(path):
            self.start_folder_size_worker(path)
        else:
            self.chart_widget.clear_chart()

    def start_folder_size_worker(self, path):
        try:
            if self.thread is not None and self.thread.isRunning():
                self.thread.quit()
                self.thread.wait()
        except RuntimeError:
            pass

        self.thread = QThread()
        self.worker = FolderSizeWorker(path)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.process)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.error.connect(self.on_worker_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.clear_thread_worker_refs)

        self.thread.start()

    def clear_thread_worker_refs(self):
        self.thread = None
        self.worker = None

    def on_worker_finished(self, data):
        folder_name = os.path.basename(self.worker.path)
        self.chart_widget.update_data(data, folder_name)

    def on_worker_error(self, error_msg):
        self.chart_widget.chart.setTitle(f"Ошибка при подсчёте размеров: {error_msg}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
