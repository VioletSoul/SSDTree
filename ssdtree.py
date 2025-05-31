import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem,
    QHBoxLayout, QWidget, QToolBar, QFileDialog, QSizePolicy
)
from PySide6.QtGui import QAction, QPainter, QColor
from PySide6.QtCharts import QChart, QChartView, QPieSeries
from PySide6.QtCore import Qt

class FileTreeWidget(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Имя", "Размер (КБ)"])
        header = self.header()
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
        self.itemSelectionChanged.connect(self.on_selection_changed)

        # Фиксируем минимальную и максимальную ширину, чтобы не растягивалась при увеличении окна
        self.setMinimumWidth(300)
        self.setMaximumWidth(600)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

    def populate(self, path):
        self.clear()
        self._add_items(path, self.invisibleRootItem())

    def _add_items(self, path, parent_item):
        try:
            entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return
        for entry in entries:
            item = QTreeWidgetItem(parent_item)
            item.setText(0, entry.name)
            if entry.is_dir(follow_symlinks=False):
                item.setText(1, "")
                self._add_items(entry.path, item)
            else:
                try:
                    size_kb = entry.stat(follow_symlinks=False).st_size / 1024
                    item.setText(1, f"{size_kb:.2f}")
                except Exception:
                    item.setText(1, "0")

    def on_selection_changed(self):
        selected = self.selectedItems()
        if selected:
            item = selected[0]
            path = self.get_full_path(item)
            if self.parent() and hasattr(self.parent(), "update_chart"):
                self.parent().update_chart(path)

    def get_full_path(self, item):
        parts = []
        while item:
            parts.insert(0, item.text(0))
            item = item.parent()
        return os.path.join(*parts)

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

    def update_data(self, path):
        self.series.clear()
        try:
            entries = list(os.scandir(path))
        except Exception:
            self.chart.setTitle("Нет доступа или папка не найдена")
            return

        data = []
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    size = self.get_folder_size(entry.path)
                else:
                    size = entry.stat(follow_symlinks=False).st_size
                if size > 0:
                    data.append((entry.name, size))
            except Exception:
                continue

        if not data:
            self.chart.setTitle("Папка пуста")
            return

        self.chart.setTitle(f"Размеры в папке: {os.path.basename(path)}")

        data_sorted = sorted(data, key=lambda x: x[1], reverse=True)
        total_size = sum(size for _, size in data_sorted)

        for i, (name, size) in enumerate(data_sorted):
            slice = self.series.append(name, size)
            slice.setBrush(self.colors[i % len(self.colors)])
            if i < 6:
                slice.setLabelVisible(True)
                percent = size / total_size * 100
                slice.setLabel(f"{name}\n{percent:.1f}%")
            else:
                slice.setLabelVisible(False)

        self.chart.legend().setVisible(True)

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

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Дерево папок и диаграммы QtCharts")
        self.resize(1000, 600)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        self.tree = FileTreeWidget(self)
        layout.addWidget(self.tree)

        self.chart_widget = PieChartWidget(self)
        layout.addWidget(self.chart_widget)

        toolbar = QToolBar()
        self.addToolBar(toolbar)
        open_action = QAction("Открыть папку", self)
        open_action.triggered.connect(self.open_folder)
        toolbar.addAction(open_action)

    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку")
        if folder:
            self.tree.populate(folder)
            self.chart_widget.update_data(folder)

    def update_chart(self, path):
        self.chart_widget.update_data(path)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
