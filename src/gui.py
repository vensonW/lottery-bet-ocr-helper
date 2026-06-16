from __future__ import annotations

import sys
import traceback
import html
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QCheckBox,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from batch_runner import BatchOptions, run_batch
from config import AppConfig, load_config, resolve_app_path, save_config


MODEL_OPTIONS = [
    "gpt-5.5",
    "gpt-5.1",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4o",
    "gpt-4o-mini",
]


class BatchWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, options: BatchOptions) -> None:
        super().__init__()
        self.options = options

    @Slot()
    def run(self) -> None:
        try:
            output = run_batch(self.options, progress_callback=self.progress.emit)
            self.finished.emit(str(output))
        except Exception:
            self.failed.emit(traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(self, root_dir: Path, resource_dir: Path | None = None) -> None:
        super().__init__()
        self.root_dir = root_dir
        self.resource_dir = resource_dir or root_dir
        self.config = load_config(root_dir)
        self.thread: QThread | None = None
        self.worker: BatchWorker | None = None

        self.setWindowTitle("批量投注图片识别小帮手")
        self.resize(860, 620)
        self._build_ui()
        self._load_config_to_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        form = QFormLayout()
        self.input_edit = QLineEdit()
        self.output_edit = QLineEdit()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_toggle_btn = QToolButton()
        self.api_key_toggle_btn.setText("👁")
        self.api_key_toggle_btn.setCheckable(True)
        self.api_key_toggle_btn.setToolTip("显示/隐藏 API Key")
        self.api_key_toggle_btn.clicked.connect(self.toggle_api_key_visibility)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(False)
        self.model_combo.addItems(MODEL_OPTIONS)
        self.base_url_edit = QLineEdit()
        self.job_spin = QSpinBox()
        self.job_spin.setRange(1, 20)
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 5)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(30, 1800)
        self.timeout_spin.setSingleStep(30)
        self.mock_check = QCheckBox("离线演示模式（不调用OpenAI）")
        self.reprocess_review_check = QCheckBox("只重新识别已有Excel中需人工核查的图片")
        self.verbose_check = QCheckBox("打印详细日志")

        input_row = QHBoxLayout()
        input_row.addWidget(self.input_edit)
        input_btn = QPushButton("选择图片文件夹")
        input_btn.clicked.connect(self.choose_input_dir)
        input_row.addWidget(input_btn)

        output_row = QHBoxLayout()
        output_row.addWidget(self.output_edit)
        output_btn = QPushButton("选择输出目录")
        output_btn.clicked.connect(self.choose_output_dir)
        output_row.addWidget(output_btn)

        api_key_row = QHBoxLayout()
        api_key_row.addWidget(self.api_key_edit)
        api_key_row.addWidget(self.api_key_toggle_btn)

        form.addRow("图片文件夹：", input_row)
        form.addRow("输出根目录：", output_row)
        form.addRow("OpenAI API Key：", api_key_row)
        form.addRow("模型：", self.model_combo)
        form.addRow("base_url：", self.base_url_edit)
        form.addRow("并发 job 数：", self.job_spin)
        form.addRow("失败重试次数：", self.retry_spin)
        form.addRow("AI超时秒数：", self.timeout_spin)
        form.addRow("", self.mock_check)
        form.addRow("", self.reprocess_review_check)
        form.addRow("", self.verbose_check)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("保存配置")
        self.save_btn.clicked.connect(self.save_current_config)
        self.start_btn = QPushButton("开始识别")
        self.start_btn.clicked.connect(self.start_batch)
        btn_row.addWidget(self.save_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.start_btn)
        layout.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        layout.addWidget(self.progress)

        layout.addWidget(QLabel("运行日志："))
        self.log = QTextBrowser()
        self.log.setReadOnly(True)
        self.log.setOpenLinks(False)
        self.log.anchorClicked.connect(self._open_log_link)
        layout.addWidget(self.log, stretch=1)

    def _load_config_to_ui(self) -> None:
        self.output_edit.setText(str(resolve_app_path(self.root_dir, self.config.default_output_dir, "outputs")))
        self.api_key_edit.setText(self.config.api_key)
        self._set_model_combo_value(self.config.model)
        self.base_url_edit.setText(self.config.base_url)
        self.job_spin.setValue(int(self.config.default_job_count or 3))
        self.retry_spin.setValue(int(self.config.retry_count or 2))
        self.timeout_spin.setValue(int(self.config.ai_timeout_seconds or 120))

    def _config_from_ui(self) -> AppConfig:
        return AppConfig(
            api_key=self.api_key_edit.text().strip(),
            model=self.model_combo.currentText().strip() or self.config.model or "gpt-5.5",
            base_url=self.base_url_edit.text().strip(),
            proxy=self.config.proxy,
            default_job_count=self.job_spin.value(),
            default_output_dir=self.output_edit.text().strip() or "outputs",
            max_image_side=self.config.max_image_side,
            retry_count=self.retry_spin.value(),
            ai_timeout_seconds=self.timeout_spin.value(),
        )

    def _set_model_combo_value(self, model: str) -> None:
        model = (model or "gpt-5.5").strip()
        if self.model_combo.findText(model) < 0:
            # 兼容 config.ini 里已经保存的自定义模型名，但界面仍不允许手动输入。
            self.model_combo.addItem(model)
        self.model_combo.setCurrentText(model)

    @Slot()
    def toggle_api_key_visibility(self) -> None:
        if self.api_key_toggle_btn.isChecked():
            self.api_key_edit.setEchoMode(QLineEdit.Normal)
            self.api_key_toggle_btn.setText("🙈")
            self.api_key_toggle_btn.setToolTip("隐藏 API Key")
        else:
            self.api_key_edit.setEchoMode(QLineEdit.Password)
            self.api_key_toggle_btn.setText("👁")
            self.api_key_toggle_btn.setToolTip("显示 API Key")

    @Slot()
    def choose_input_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择图片文件夹", str(self.root_dir))
        if folder:
            self.input_edit.setText(folder)

    @Slot()
    def choose_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择输出根目录", str(self.root_dir / "outputs"))
        if folder:
            self.output_edit.setText(folder)

    @Slot()
    def save_current_config(self) -> None:
        self.config = self._config_from_ui()
        save_config(self.root_dir, self.config)
        QMessageBox.information(self, "已保存", "配置已保存到 config.ini")

    @Slot()
    def start_batch(self) -> None:
        input_dir = Path(self.input_edit.text().strip())
        if not input_dir.exists():
            QMessageBox.warning(self, "错误", "请选择有效的图片文件夹")
            return
        self.config = self._config_from_ui()
        api_key = self.config.resolved_api_key()
        if not api_key and not self.mock_check.isChecked():
            QMessageBox.warning(self, "错误", "config.ini 中缺少 OpenAI API Key，请先配置后再运行。")
            return

        save_config(self.root_dir, self.config)
        output_root = resolve_app_path(self.root_dir, self.config.default_output_dir, "outputs")
        options = BatchOptions(
            input_dir=input_dir,
            output_dir=output_root / input_dir.name / "识别结果",
            job_count=self.config.default_job_count,
            api_key=api_key or "mock",
            model=self.config.model,
            skill_path=self.resource_dir / "skills" / "lottery_ocr" / "SKILL.md",
            output_name=f"投注识别统计_{input_dir.name}",
            base_url=self.config.base_url,
            proxy=self.config.proxy,
            max_image_side=self.config.max_image_side,
            retry_count=self.config.retry_count,
            mock=self.mock_check.isChecked(),
            verbose=self.verbose_check.isChecked(),
            ai_timeout_seconds=self.config.ai_timeout_seconds,
            reprocess_review=self.reprocess_review_check.isChecked(),
        )
        self.start_btn.setEnabled(False)
        self.progress.setValue(0)
        self.log.clear()
        self._log("开始处理...")

        self.thread = QThread(self)
        self.worker = BatchWorker(options)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    @Slot(int, int, str)
    def on_progress(self, done: int, total: int, message: str) -> None:
        if total:
            self.progress.setValue(int(done * 100 / total))
        prefix = f"[{done}/{total}] " if total else ""
        self._log(f"{prefix}{message}")

    @Slot(str)
    def on_finished(self, output_file: str) -> None:
        self.start_btn.setEnabled(True)
        self.progress.setValue(100)
        self._log_with_link("[完成] 完成：", output_file)
        QMessageBox.information(self, "完成", f"Excel已生成：\n{output_file}")

    @Slot(str)
    def on_failed(self, error: str) -> None:
        self.start_btn.setEnabled(True)
        self._log(error)
        QMessageBox.critical(self, "处理失败", error)

    def _log(self, message: str) -> None:
        self.log.append(html.escape(message).replace("\n", "<br>"))

    def _log_with_link(self, prefix: str, path_text: str) -> None:
        url = QUrl.fromLocalFile(path_text).toString()
        prefix_html = html.escape(prefix)
        path_html = html.escape(path_text)
        url_html = html.escape(url, quote=True)
        self.log.append(f'{prefix_html}<a href="{url_html}">{path_html}</a>')

    @Slot(QUrl)
    def _open_log_link(self, url: QUrl) -> None:
        QDesktopServices.openUrl(url)


def main(root_dir: Path, resource_dir: Path | None = None) -> int:
    app = QApplication(sys.argv)
    win = MainWindow(root_dir, resource_dir)
    win.show()
    return app.exec()
