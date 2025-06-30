# Folder Tree with QtCharts Diagrams on PySide6

![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-41CD52?style=flat&logo=qt&logoColor=white)
![QtCharts](https://img.shields.io/badge/QtCharts-✓-blue)
![Async](https://img.shields.io/badge/Async-Threaded-brightgreen)
![Cross-platform](https://img.shields.io/badge/Cross--platform-✓-orange)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Repo Size](https://img.shields.io/github/repo-size/VioletSoul/SSDTree)
![Code Size](https://img.shields.io/github/languages/code-size/VioletSoul/SSDTree)
[![Stars](https://img.shields.io/github/stars/VioletSoul/SSDTree.svg?style=social)](https://github.com/VioletSoul/SSDTree)
[![Last Commit](https://img.shields.io/github/last-commit/VioletSoul/SSDTree.svg)](https://github.com/VioletSoul/SSDTree/commits/main)

A Python application using PySide6 that displays a sortable folder tree and visualizes file and folder sizes with a pie chart.

---

## Description

This program allows you to:

- Browse the contents of a selected folder as a tree with file names and sizes.
- Sort items by name, size, creation date, or type.
- When selecting a folder, display a pie chart showing the size distribution of files and subfolders.
- When selecting a file, show its properties as an overlay on top of the chart.
- Calculate sizes in a separate thread to keep the UI responsive.

---

## Main Features

- **Folder tree** with two columns: name and size (in KB).
- **Sorting** in four modes:
  - By name
  - By size
  - By creation date
  - By file type (extension)
- **QtCharts pie chart** for visual representation of each file and folder's share.
- **Information overlay** with detailed properties of the selected file.
- **Asynchronous folder size calculation** with the ability to interrupt.
- Convenient interface with a toolbar for folder selection.

---

## Technologies Used

- Python 3
- PySide6 (Qt for Python)
- `QtCharts` module for charting
- Multithreading using `QThread` and `QObject`

---

## Launch

1. Install dependencies (if not already installed):
    ```
    pip install PySide6
    ```
2. Run the script:
    ```
    python3 ssdtree.py
    ```
3. In the main window, select a folder using the "Open Folder" button.
4. Explore the contents and visualization.

---

## Code Structure

- `human_readable_size(size_bytes)` — function to format size in a human-readable way (B, KB, MB, GB).
- `SortableTreeWidgetItem` — tree item supporting sorting by different criteria.
- `FileTreeWidget` — folder tree widget with selection and sorting capabilities.
- `FolderSizeWorker` — worker object for calculating folder sizes in a separate thread.
- `PieChartWidget` — pie chart widget displaying element sizes.
- `InfoOverlay` — overlay for showing selected file properties.
- `MainWindow` — main application window combining all components and managing logic.

---

## Usage Example

- Select a folder for analysis.
- In the tree on the left, select a folder or file.
- For a folder, a chart with size distribution will appear on the right.
- For a file, a window with its properties (size, dates, permissions, etc.) will appear.
- Change the sorting mode via the dropdown menu.

---

## License

This project is provided "as is" with no warranties. Free to use and modify.

---

## Contacts & Support

For questions and suggestions, create an issue or pull request in the repository.

---
Thank you for using!
---
