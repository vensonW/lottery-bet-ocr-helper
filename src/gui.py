from __future__ import annotations

import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from batch_runner import BatchOptions, run_batch
from config import AppConfig, load_config, resolve_app_path, save_config


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
    def __init__(self, root_dir: Path) -> None:
        super().__init__()
        self.root_dir = root_dir
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
        self.model_edit = QLineEdit()
        self.job_spin = QSpinBox()
        self.job_spin.setRange(1, 20)
        self.max_side_spin = QSpinBox()
        self.max_side_spin.setRange(512, 6000)
        self.max_side_spin.setSingleStep(256)
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 5)
        self.mock_check = QCheckBox("离线演示模式（不调用OpenAI）")

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

        form.addRow("图片文件夹：", input_row)
        form.addRow("输出目录：", output_row)
        form.addRow("OpenAI API Key：", self.api_key_edit)
        form.addRow("模型：", self.model_edit)
        form.addRow("并发 job 数：", self.job_spin)
        form.addRow("图片最长边：", self.max_side_spin)
        form.addRow("失败重试次数：", self.retry_spin)
        form.addRow("", self.mock_check)
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
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, stretch=1)

    def _load_config_to_ui(self) -> None:
        self.output_edit.setText(str(resolve_app_path(self.root_dir, self.config.default_output_dir, "outputs")))
        self.api_key_edit.setText(self.config.api_key)
        self.model_edit.setText(self.config.model)
        self.job_spin.setValue(int(self.config.default_job_count or 3))
        self.max_side_spin.setValue(int(self.config.max_image_side or 2048))
        self.retry_spin.setValue(int(self.config.retry_count or 2))

    def _config_from_ui(self) -> AppConfig:
        return AppConfig(
            api_key=self.api_key_edit.text().strip(),
            model=self.model_edit.text().strip() or "gpt-5.5",
            default_job_count=self.job_spin.value(),
            default_output_dir=self.output_edit.text().strip() or "outputs",
            max_image_side=self.max_side_spin.value(),
            retry_count=self.retry_spin.value(),
        )

    @Slot()
    def choose_input_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择图片文件夹", str(self.root_dir))
        if folder:
            self.input_edit.setText(folder)

    @Slot()
    def choose_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录", str(self.root_dir / "outputs"))
        if folder:
            self.output_edit.setText(folder)

    @Slot()
    def save_current_config(self) -> None:
        self.config = self._config_from_ui()
        save_config(self.root_dir, self.config)
        QMessageBox.information(self, "已保存", "配置已保存到 config.json")

    @Slot()
    def start_batch(self) -> None:
        input_dir = Path(self.input_edit.text().strip())
        if not input_dir.exists():
            QMessageBox.warning(self, "错误", "请选择有效的图片文件夹")
            return
        self.config = self._config_from_ui()
        api_key = self.config.resolved_api_key()
        if not api_key and not self.mock_check.isChecked():
            QMessageBox.warning(self, "错误", "请填写 OpenAI API Key，或设置环境变量 OPENAI_API_KEY")
            return

        save_config(self.root_dir, self.config)
        options = BatchOptions(
            input_dir=input_dir,
            output_dir=resolve_app_path(self.root_dir, self.config.default_output_dir, "outputs"),
            job_count=self.config.default_job_count,
            api_key=api_key or "mock",
            model=self.config.model,
            skill_path=self.root_dir / "skills" / "lottery_ocr" / "SKILL.md",
            max_image_side=self.config.max_image_side,
            retry_count=self.config.retry_count,
            mock=self.mock_check.isChecked(),
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
        self._log(message)

    @Slot(str)
    def on_finished(self, output_file: str) -> None:
        self.start_btn.setEnabled(True)
        self.progress.setValue(100)
        self._log(f"完成：{output_file}")
        QMessageBox.information(self, "完成", f"Excel已生成：\n{output_file}")

    @Slot(str)
    def on_failed(self, error: str) -> None:
        self.start_btn.setEnabled(True)
        self._log(error)
        QMessageBox.critical(self, "处理失败", error)

    def _log(self, message: str) -> None:
        self.log.append(message)


def main(root_dir: Path) -> int:
    app = QApplication(sys.argv)
    win = MainWindow(root_dir)
    win.show()
    return app.exec()
