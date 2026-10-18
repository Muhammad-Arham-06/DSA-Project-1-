"""
Movies Explorer - DSA Project 1

Shows films scraped from Wikipedia in a PyQt table. The user can sort (11 algorithms),
benchmark, search and filter them. Needs sorting.py, searching.py, scraper.py and movies.csv
in the same folder.

Run:  python3 main.py
"""
import os
import sys
import threading

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                             QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                             QLineEdit, QMainWindow, QMessageBox,
                             QProgressBar, QPushButton, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from scraper import (COLUMNS, END_YEAR, START_YEAR, load_movies, make_session,
                     row_key, save_csv, scrape_url, scrape_year)
from searching import OPERATORS, SEARCH_ALGOS, apply_conditions
from sorting import (ALGORITHMS, NUMERIC_ONLY, SLOW, benchmark,
                     describe_levels, run_sort)

SCRAPE_TARGET = 15000            # the progress bar is measured against this


# ======================================================================
# Background workers (so the window never freezes)
# ======================================================================
class SortWorker(QThread):
    done = pyqtSignal(object, int, int, float)
    failed = pyqtSignal(str)

    def __init__(self, rows, levels, algo):
        super().__init__()
        self.rows, self.levels, self.algo = rows, levels, algo

    def run(self):
        try:
            result, comps, swaps, ms = run_sort(self.rows, self.levels, self.algo)
        except ValueError as e:
            self.failed.emit(str(e))
            return
        self.done.emit(result, comps, swaps, ms)


class BenchWorker(QThread):
    progress = pyqtSignal(str)
    done = pyqtSignal(object)

    def __init__(self, rows, levels):
        super().__init__()
        self.rows, self.levels = rows, levels

    def run(self):
        self.done.emit(benchmark(self.rows, self.levels, progress=self.progress.emit))


class ScrapeWorker(QThread):
    progress = pyqtSignal(int, int)          # films scraped so far, current year
    done_signal = pyqtSignal(object, bool)   # rows, stopped?

    def __init__(self):
        super().__init__()
        self.running = threading.Event()
        self.running.set()                   # set = running, cleared = paused
        self.stop_flag = False

    def pause(self):
        self.running.clear()

    def resume(self):
        self.running.set()

    def stop(self):
        self.stop_flag = True
        self.running.set()                   # wake the thread even if it is paused

    def run(self):
        session = make_session()
        rows, seen = [], set()
        for year in range(START_YEAR, END_YEAR + 1):
            self.running.wait()              # blocks here while paused
            if self.stop_flag:
                break
            try:
                for m in scrape_year(year, session):
                    if row_key(m) not in seen:
                        seen.add(row_key(m))
                        rows.append(m)
            except Exception as e:
                print(year, "error:", e)
            self.progress.emit(len(rows), year)
        save_csv(rows, "movies_scraped.csv")
        self.done_signal.emit(rows, self.stop_flag)


class UrlWorker(QThread):
    done = pyqtSignal(object, str)           # rows, error message

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            self.done.emit(scrape_url(self.url, make_session()), "")
        except Exception as e:
            self.done.emit([], str(e))




# ======================================================================
# User interface
# ======================================================================
class ConditionRow(QWidget):
    """One filter condition: [AND/OR] [NOT] column operator value [X]"""

    def __init__(self, columns, on_remove):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.connector = QComboBox()
        self.connector.addItems(["AND", "OR"])
        self.not_box = QCheckBox("NOT")
        self.col = QComboBox()
        self.col.addItems(columns)
        self.op = QComboBox()
        self.op.addItems(OPERATORS)
        self.text = QLineEdit()
        self.text.setPlaceholderText("value")
        self.remove_btn = QPushButton("X")
        self.remove_btn.setFixedWidth(30)
        self.remove_btn.clicked.connect(lambda: on_remove(self))
        for w in (self.connector, self.not_box, self.col, self.op, self.text, self.remove_btn):
            layout.addWidget(w)

    def get(self):
        return {"connector": self.connector.currentText(),
                "negate": self.not_box.isChecked(),
                "col": self.col.currentText(),
                "op": self.op.currentText(),
                "query": self.text.text().strip()}


class BenchDialog(QDialog):
    def __init__(self, parent, results, title):
        super().__init__(parent)
        self.setWindowTitle("Benchmark: " + title)
        self.resize(950, 440)
        headers = ["Algorithm", "Time (ms)", "Comparisons", "Swaps / Moves",
                   "Time complexity", "Stable?"]
        table = QTableWidget(len(results), len(headers))
        table.setHorizontalHeaderLabels(headers)
        for i, (name, ms, comps, swaps, cx, stable) in enumerate(results):
            if ms is None:
                numbers = ["N/A", "N/A", "N/A"]
            else:
                numbers = [f"{ms:,.2f}", f"{comps:,}", f"{swaps:,}"]
            values = [name] + numbers + [cx, "Yes" if stable else "No"]
            for j, v in enumerate(values):
                table.setItem(i, j, QTableWidgetItem(v))
        table.setColumnWidth(0, 140)
        table.setColumnWidth(4, 230)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Merge/Hybrid/Counting/Radix/Bucket sort do not swap, so 'swaps' counts element moves. "
            "Counting and Radix sort compare no keys (0 comparisons). "
            "N/A = the algorithm cannot sort this column."))
        layout.addWidget(table)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Movies Explorer")
        self.resize(1400, 900)

        self.all_rows = load_movies("movies.csv") if os.path.exists("movies.csv") else []
        self.filtered = None                 # None = no filter active
        self.columns = COLUMNS
        self.cond_rows = []
        self.header_state = (None, False)    # (column, descending) of the last header click
        self.worker = None
        self.bench_worker = None
        self.scrape_worker = None
        self.url_worker = None

        central = QWidget()
        self.setCentralWidget(central)
        main = QVBoxLayout(central)
        main.addWidget(self.build_sort_group())
        main.addWidget(self.build_search_group())
        main.addWidget(self.build_scrape_group())

        self.result_label = QLabel("")
        self.status = QLabel()
        self.table = QTableWidget()
        self.table.horizontalHeader().sectionClicked.connect(self.header_clicked)
        main.addWidget(self.result_label)
        main.addWidget(self.status)
        main.addWidget(self.table, 1)

        self.update_algo_info()
        self.add_condition()
        self.show_rows(self.all_rows)
        if not self.all_rows:
            self.result_label.setText("No data loaded. Press Start to scrape the movies.")

    # ---------------------------------------------------------- sorting
    def build_sort_group(self):
        box = QGroupBox("Sorting (click a column header to sort by that column)")
        g = QGridLayout(box)

        self.scope_box = QComboBox()
        self.scope_box.addItems(["Full dataset", "Filtered results"])
        self.algo_box = QComboBox()
        self.algo_box.addItems(list(ALGORITHMS.keys()))
        self.algo_box.currentTextChanged.connect(self.update_algo_info)
        self.algo_info = QLabel()

        g.addWidget(QLabel("Sort scope:"), 0, 0)
        g.addWidget(self.scope_box, 0, 1)
        g.addWidget(QLabel("Algorithm:"), 0, 2)
        g.addWidget(self.algo_box, 0, 3)
        g.addWidget(self.algo_info, 0, 4, 1, 3)

        self.col_boxes, self.order_boxes = [], []
        for level in range(3):
            cb = QComboBox()
            cb.addItems(self.columns if level == 0 else ["(none)"] + self.columns)
            ob = QComboBox()
            ob.addItems(["Ascending", "Descending"])
            self.col_boxes.append(cb)
            self.order_boxes.append(ob)
            g.addWidget(QLabel(f"Level {level + 1}:"), level + 1, 0)
            g.addWidget(cb, level + 1, 1)
            g.addWidget(ob, level + 1, 2)

        self.sort_btn = QPushButton("Sort")
        self.sort_btn.clicked.connect(self.start_sort)
        self.bench_btn = QPushButton("Benchmark (all algorithms)")
        self.bench_btn.clicked.connect(self.start_benchmark)
        g.addWidget(self.sort_btn, 1, 3)
        g.addWidget(self.bench_btn, 2, 3)
        return box

    def update_algo_info(self):
        name = self.algo_box.currentText()
        _, complexity, stable = ALGORITHMS[name]
        extra = " | single numeric column only" if name in NUMERIC_ONLY else ""
        self.algo_info.setText(f"Time: {complexity} | Stable: {'Yes' if stable else 'No'}{extra}")

    def get_levels(self):
        levels = [(self.col_boxes[0].currentText(),
                   self.order_boxes[0].currentText() == "Descending")]
        for i in (1, 2):
            col = self.col_boxes[i].currentText()
            if col != "(none)":
                levels.append((col, self.order_boxes[i].currentText() == "Descending"))
        return levels

    def rows_for_scope(self):
        if self.scope_box.currentText() == "Filtered results" and self.filtered is not None:
            return self.filtered, "filtered"
        return self.all_rows, "full"

    def set_busy(self, busy):
        for b in (self.sort_btn, self.bench_btn, self.apply_btn, self.clear_btn):
            b.setEnabled(not busy)

    def check_ready(self, rows):
        """Common checks before sorting or benchmarking."""
        if not rows:
            QMessageBox.warning(self, "No data", "There are no rows to work with.")
            return False
        return True

    def start_sort(self):
        rows, scope = self.rows_for_scope()
        if not self.check_ready(rows):
            return
        algo = self.algo_box.currentText()
        levels = self.get_levels()
        if algo in NUMERIC_ONLY and (len(levels) > 1 or
                                     not isinstance(rows[0][levels[0][0]], (int, float))):
            QMessageBox.warning(self, "Sort", f"{algo} works only on a single numeric column.")
            return
        if algo in SLOW and len(rows) > 5000:
            ans = QMessageBox.question(
                self, "Slow algorithm",
                f"{algo} on {len(rows):,} rows may take 10-60 seconds or more. Continue?")
            if ans != QMessageBox.StandardButton.Yes:
                return
        self.set_busy(True)
        self.result_label.setText(f"Sorting with {algo}... (please wait)")
        self.worker = SortWorker(rows, levels, algo)
        self.worker.done.connect(
            lambda r, c, s, ms: self.sort_done(r, c, s, ms, algo, levels, scope))
        self.worker.failed.connect(self.sort_failed)
        self.worker.start()

    def sort_failed(self, message):
        self.set_busy(False)
        self.result_label.setText("")
        QMessageBox.warning(self, "Sort", f"This algorithm cannot sort that column: {message}")

    def sort_done(self, result, comps, swaps, ms, algo, levels, scope):
        note = ""
        if scope == "filtered":
            self.filtered = result
        else:
            if self.filtered is not None:
                note = " | (filter cleared, full dataset is shown)"
            self.all_rows = result
            self.filtered = None
        self.show_rows(result)
        self.result_label.setText(
            f"{algo} on [{describe_levels(levels)}] ({scope}): {ms:,.2f} ms | "
            f"comparisons: {comps:,} | swaps: {swaps:,}{note}")
        self.set_busy(False)

    def header_clicked(self, index):
        """Clicking a column header sorts by that column with the selected algorithm;
        clicking the same header again reverses the order."""
        if not self.sort_btn.isEnabled() or index >= len(self.columns):
            return
        column = self.columns[index]
        last_column, last_desc = self.header_state
        descending = (not last_desc) if column == last_column else False
        self.header_state = (column, descending)
        self.col_boxes[0].setCurrentText(column)
        self.order_boxes[0].setCurrentText("Descending" if descending else "Ascending")
        self.col_boxes[1].setCurrentText("(none)")
        self.col_boxes[2].setCurrentText("(none)")
        self.start_sort()

    # ---------------------------------------------------------- benchmark
    def start_benchmark(self):
        rows, scope = self.rows_for_scope()
        if not self.check_ready(rows):
            return
        levels = self.get_levels()
        if len(rows) > 5000:
            ans = QMessageBox.question(
                self, "Benchmark",
                f"All {len(ALGORITHMS)} algorithms will run on {len(rows):,} rows "
                "(including the slow ones). This may take a few minutes. Continue?")
            if ans != QMessageBox.StandardButton.Yes:
                return
        self.set_busy(True)
        self.bench_worker = BenchWorker(rows, levels)
        self.bench_worker.progress.connect(
            lambda name: self.result_label.setText(f"Benchmark running: {name}..."))
        self.bench_worker.done.connect(
            lambda res: self.bench_done(res, f"{describe_levels(levels)} | {len(rows):,} rows"))
        self.bench_worker.start()

    def bench_done(self, results, title):
        self.set_busy(False)
        self.result_label.setText("Benchmark complete")
        BenchDialog(self, results, title).exec()

    # ---------------------------------------------------------- searching
    def build_search_group(self):
        box = QGroupBox("Search / Filter (conditions are combined from left to right)")
        layout = QVBoxLayout(box)

        top = QHBoxLayout()
        self.search_algo = QComboBox()
        self.search_algo.addItems(SEARCH_ALGOS)
        top.addWidget(QLabel("Search algorithm:"))
        top.addWidget(self.search_algo)
        self.add_btn = QPushButton("+ Add condition")
        self.add_btn.clicked.connect(self.add_condition)
        self.apply_btn = QPushButton("Apply filter")
        self.apply_btn.clicked.connect(self.apply_filter)
        self.clear_btn = QPushButton("Clear filter")
        self.clear_btn.clicked.connect(self.clear_filter)
        for b in (self.add_btn, self.apply_btn, self.clear_btn):
            top.addWidget(b)
        top.addStretch()
        layout.addLayout(top)

        self.cond_layout = QVBoxLayout()
        layout.addLayout(self.cond_layout)
        return box

    def add_condition(self):
        row = ConditionRow(self.columns, self.remove_condition)
        self.cond_rows.append(row)
        self.cond_layout.addWidget(row)
        self.refresh_connectors()

    def remove_condition(self, row):
        if len(self.cond_rows) == 1:
            row.text.clear()
            return
        self.cond_rows.remove(row)
        self.cond_layout.removeWidget(row)
        row.deleteLater()
        self.refresh_connectors()

    def refresh_connectors(self):
        for i, r in enumerate(self.cond_rows):
            r.connector.setVisible(i > 0)        # the first condition has no AND/OR

    def apply_filter(self):
        if not self.check_ready(self.all_rows):
            return
        conds = [r.get() for r in self.cond_rows]
        if any(not c["query"] for c in conds):
            QMessageBox.warning(self, "Filter",
                                "Enter a value in every condition (or remove the empty condition).")
            return
        algo = self.search_algo.currentText()
        try:
            out, comps, ms = apply_conditions(self.all_rows, conds, algo)
        except ValueError:
            QMessageBox.warning(self, "Filter", "Enter a number for numeric columns (for example 1999).")
            return
        self.filtered = out
        self.show_rows(out)
        extra = ""
        if algo == "Binary Search" and any(c["op"] != "equals" for c in conds):
            extra = " | (Binary Search applies only to 'equals'; other operators use Linear Search)"
        self.result_label.setText(
            f"Filter: {len(out):,} results | {algo} | comparisons: {comps:,} | {ms:,.2f} ms{extra}")

    def clear_filter(self):
        self.filtered = None
        self.show_rows(self.all_rows)
        self.result_label.setText("Filter cleared")

    # ---------------------------------------------------------- scraper
    def build_scrape_group(self):
        box = QGroupBox("Scraper (Wikipedia, BeautifulSoup)")
        layout = QVBoxLayout(box)

        controls = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.pause_btn = QPushButton("Pause")
        self.resume_btn = QPushButton("Resume")
        self.stop_btn = QPushButton("Stop")
        self.start_btn.clicked.connect(self.scrape_start)
        self.pause_btn.clicked.connect(self.scrape_pause)
        self.resume_btn.clicked.connect(self.scrape_resume)
        self.stop_btn.clicked.connect(self.scrape_stop)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, SCRAPE_TARGET)
        self.scrape_label = QLabel("Ready")
        for w in (self.start_btn, self.pause_btn, self.resume_btn, self.stop_btn,
                  self.progress_bar, self.scrape_label):
            controls.addWidget(w)
        layout.addLayout(controls)

        url_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(
            "Paste a Wikipedia page URL, e.g. https://en.wikipedia.org/wiki/List_of_American_films_of_2005")
        self.url_btn = QPushButton("Scrape URL")
        self.url_btn.clicked.connect(self.scrape_from_url)
        url_row.addWidget(QLabel("URL:"))
        url_row.addWidget(self.url_edit, 1)
        url_row.addWidget(self.url_btn)
        layout.addLayout(url_row)

        self.scrape_buttons(running=False, paused=False)
        return box

    def scrape_buttons(self, running, paused):
        self.start_btn.setEnabled(not running)
        self.pause_btn.setEnabled(running and not paused)
        self.resume_btn.setEnabled(running and paused)
        self.stop_btn.setEnabled(running)

    def scrape_start(self):
        self.scrape_worker = ScrapeWorker()
        self.scrape_worker.progress.connect(self.scrape_progress)
        self.scrape_worker.done_signal.connect(self.scrape_done)
        self.progress_bar.setValue(0)
        self.scrape_label.setText("Scraping started...")
        self.scrape_buttons(running=True, paused=False)
        self.scrape_worker.start()

    def scrape_pause(self):
        self.scrape_worker.pause()
        self.scrape_label.setText(self.scrape_label.text() + " | PAUSED (stops after the current year finishes)")
        self.scrape_buttons(running=True, paused=True)

    def scrape_resume(self):
        self.scrape_worker.resume()
        self.scrape_buttons(running=True, paused=False)

    def scrape_stop(self):
        self.scrape_worker.stop()
        self.scrape_label.setText("Stopping...")

    def scrape_progress(self, total, year):
        self.progress_bar.setValue(min(total, SCRAPE_TARGET))
        self.scrape_label.setText(f"Scraped: {total:,} entities | year {year}")

    def scrape_done(self, rows, stopped):
        self.scrape_buttons(running=False, paused=False)
        self.scrape_label.setText(
            f"{'Stopped' if stopped else 'Done'}: {len(rows):,} entities (saved to movies_scraped.csv)")
        if rows:
            self.all_rows = rows
            self.filtered = None
            self.show_rows(rows)

    def scrape_from_url(self):
        url = self.url_edit.text().strip()
        if not url.startswith("http"):
            QMessageBox.warning(self, "URL", "Enter a full URL starting with http:// or https://")
            return
        self.url_btn.setEnabled(False)
        self.scrape_label.setText("Scraping URL...")
        self.url_worker = UrlWorker(url)
        self.url_worker.done.connect(self.url_done)
        self.url_worker.start()

    def url_done(self, rows, error):
        self.url_btn.setEnabled(True)
        if error:
            self.scrape_label.setText("URL failed")
            QMessageBox.warning(self, "URL", f"Could not scrape that URL: {error}")
            return
        if not rows:
            self.scrape_label.setText("No movie table found on that page")
            return
        known = {row_key(r) for r in self.all_rows}
        new_rows = [r for r in rows if row_key(r) not in known]
        self.all_rows.extend(new_rows)
        self.filtered = None
        self.show_rows(self.all_rows)
        self.scrape_label.setText(f"URL scraped: {len(rows):,} films found, {len(new_rows):,} new")

    # ---------------------------------------------------------- table
    def show_rows(self, rows):
        self.table.setUpdatesEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(self.columns))
        self.table.setRowCount(len(rows))
        self.table.setHorizontalHeaderLabels(self.columns)
        for i, row in enumerate(rows):
            for j, col in enumerate(self.columns):
                item = QTableWidgetItem(str(row[col]))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(i, j, item)
        self.table.setColumnWidth(0, 280)
        self.table.setColumnWidth(4, 220)
        self.table.setColumnWidth(5, 160)
        self.table.setColumnWidth(6, 350)
        self.table.setUpdatesEnabled(True)
        self.status.setText(f"Showing {len(rows):,} movies (total dataset: {len(self.all_rows):,})")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())