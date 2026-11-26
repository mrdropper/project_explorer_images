import sys
from PyQt6 import uic
from PyQt6.QtCore import Qt, QPoint, QRect
from PyQt6.QtWidgets import QApplication, QMainWindow, QFileDialog, QMessageBox, QTableWidgetItem, QHeaderView, \
    QTableWidget, QInputDialog, QMenu, QWidget, QLabel, QColorDialog
from PyQt6.QtGui import QAction, QImage, QPixmap, QPainter, QPen, QTransform, QColor
import csv
import sqlite3
import os
import datetime


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi('mainmenu.ui', self)
        self.setWindowTitle('Проводник работы с изображениями')
        self.setFixedSize(self.size())

        self.features = None
        self.OpenedImg = None
        self.redactor = None

        self.add_img.clicked.connect(lambda: self.add_image())
        self.del_all.clicked.connect(self.delete_all)
        self.save_csv.clicked.connect(self.save_csv_file)

        self.table_img.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_img.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_img.cellDoubleClicked.connect(self.view_img)
        self.table_img.customContextMenuRequested.connect(self.open_menu)

        self.update_table()

    def open_menu(self, pos):
        item = self.table_img.itemAt(pos)
        if not item:
            return
        row = item.row()
        id_ = self.table_img.item(row, 0).text()

        menu = QMenu(self)
        change_f = QAction("Изменить", self)
        rename_f = QAction("Переименовать", self)
        delete_f = QAction("Удалить", self)
        features_f = QAction("Свойства", self)
        change_f.triggered.connect(lambda: self.open_redactor(id_))
        rename_f.triggered.connect(lambda: self.rename(row))
        delete_f.triggered.connect(lambda: self.delete_image(id_))
        features_f.triggered.connect(lambda: self.view_features(id_))
        menu.addAction(change_f)
        menu.addAction(rename_f)
        menu.addAction(features_f)
        menu.addAction(delete_f)

        menu.exec(self.table_img.viewport().mapToGlobal(pos))

    def rename(self, row):
        id_ = self.table_img.item(row, 0).text()
        con = sqlite3.connect('app_data.db')
        cur = con.cursor()
        cur_name_no_type_no_n_copy = cur.execute("""SELECT name FROM name_details
        WHERE id = ?""", (id_,)).fetchone()[0]
        type_ = cur.execute("""SELECT type FROM name_details
        WHERE id = ?""", (id_,)).fetchone()[0]
        old_full_name, old_path = cur.execute("""SELECT full_name, path FROM images
        WHERE id = ?""", (id_,)).fetchone()

        new_name, ok = QInputDialog.getText(self, "Изменить название",
                                            "Введите новое название:", text=cur_name_no_type_no_n_copy)
        if len(new_name) > 251:
            QMessageBox.critical(self, 'Ошибка', 'Слишком длинное название!')
            con.close()
            return

        n_copy = None
        n_copies = cur.execute("""SELECT n_copy FROM name_details
        WHERE name = ? AND type = ?""", (new_name, type_)).fetchall()

        n_copies = [i[0] for i in n_copies]
        if n_copies:
            for i in range(max(n_copies) + 2):
                if i not in n_copies:
                    n_copy = i
                    break
        if ok and new_name != cur_name_no_type_no_n_copy:
            new_full_name = f"{new_name}.{type_}"
            if n_copy is not None:
                QMessageBox.warning(self, 'Предупреждение', 'Изображение с таким именем уже существует.')
                if n_copy > 0:
                    new_full_name = f"{new_name} ({n_copy}).{type_}"

            file_n_copy = n_copy if n_copy is not None else 0
            while (cur.execute("SELECT 1 FROM images WHERE full_name = ? AND id != ?",
                               (new_full_name, id_)).fetchone()
                   or os.path.exists(f"{old_path}/{new_full_name}")):
                file_n_copy += 1
                new_full_name = f"{new_name} ({file_n_copy}).{type_}"
                n_copy = file_n_copy

            old_file_path = f"{old_path}/{old_full_name}"
            orig_file_path = f"{old_path}/{cur_name_no_type_no_n_copy}.{type_}"
            new_file_path = f"{old_path}/{new_full_name}"

            has_other_copies = cur.execute("""
                SELECT 1 FROM name_details nd
                JOIN images img ON nd.id = img.id
                WHERE nd.name = ? AND nd.type = ? AND img.path = ? AND nd.id != ?
            """, (cur_name_no_type_no_n_copy, type_, old_path, id_)).fetchone()

            try:
                if os.path.exists(old_file_path) and not has_other_copies:
                    os.rename(old_file_path, new_file_path)
                elif os.path.exists(old_file_path):
                    with open(old_file_path, 'rb') as f_reading, open(new_file_path, 'wb') as f_creating:
                        f_creating.write(f_reading.read())
                        QMessageBox.warning(
                            self,
                            'Предупреждение',
                            'У этого изображения есть копии в базе данных, '
                            'поэтому на диске создан новый файл, а исходный сохранён.')
                elif os.path.exists(orig_file_path):
                    with open(orig_file_path, 'rb') as f_reading, open(new_file_path, 'wb') as f_creating:
                        f_creating.write(f_reading.read())
                        QMessageBox.warning(self, 'Предупреждение',
                                            'Для переименования копии на диске создан файл на основе оригинала.')
                else:
                    QMessageBox.critical(self, 'Ошибка', 'Не удалось переименовать файл на диске: файл не найден')
                    con.close()
                    return
            except OSError as er:
                QMessageBox.critical(self, 'Ошибка', f'Не удалось переименовать файл на диске:\n{er}')
                con.close()
                return

            cur.execute("UPDATE images SET full_name = ? WHERE id = ?", (new_full_name, id_))
            cur.execute("""UPDATE name_details SET name = ?, n_copy = ?
            WHERE id = ?""", (new_name, n_copy if n_copy is not None else 0, id_))
            con.commit()
        con.close()
        self.update_table()

    def update_table(self):
        con = sqlite3.connect('app_data.db')
        cur = con.cursor()
        rows = cur.execute("SELECT * FROM images").fetchall()
        headers = [i[0] for i in cur.description]
        rows = [headers] + rows
        con.close()

        self.table_img.clear()
        self.table_img.setRowCount(len(rows) - 1 if len(rows) > 0 else 0)
        self.table_img.setColumnCount(len(rows[0]))
        self.table_img.setHorizontalHeaderLabels(rows[0])
        for i, row in enumerate(rows[1:]):
            for j, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                if val:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table_img.setItem(i, j, item)
        header = self.table_img.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)

    def add_image(self, fs_data=None):
        if not fs_data:
            fs_data = QFileDialog.getOpenFileNames(self,
                                                   'Выбрать изображение', '',
                                                   'Изображения (*.png *.jpg *.webp *.jpeg)')[0]
        if fs_data:
            n_copy_cnt = 0
            for f_data in fs_data:
                full_name = f_data.split("/")[-1]
                name = ".".join(full_name.split(".")[:-1])
                type_ = full_name.split(".")[-1]
                path = "/".join(f_data.split("/")[:-1])
                size = os.path.getsize(f_data)

                timestamp = os.path.getmtime(f_data)
                date = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')

                con = sqlite3.connect('app_data.db')
                cur = con.cursor()
                n_copy = 0
                n_copies = cur.execute("""SELECT n_copy FROM name_details
                            WHERE name = ? AND type = ?""", (name, type_)).fetchall()
                n_copies = [i[0] for i in n_copies]
                if n_copies:
                    for i in range(max(n_copies) + 2):
                        if i not in n_copies:
                            n_copy = i
                            break
                if n_copy > 0:
                    full_name = f"{name} ({n_copy}).{type_}"
                    n_copy_cnt += 1

                while cur.execute("""SELECT 1 FROM images
                WHERE full_name = ?""", (full_name,)).fetchone():
                    if n_copy == 0:
                        n_copy_cnt += 1
                    n_copy += 1
                    full_name = f"{name} ({n_copy}).{type_}"

                if len(name) > 251:
                    QMessageBox.critical(self, 'Ошибка', 'Слишком длинное название!')
                    con.close()
                    continue

                cur.execute("""INSERT INTO images(full_name, path, size, date)
                VALUES(?, ?, ?, ?)""", (full_name, path, size, date))
                new_id = cur.lastrowid
                cur.execute("""INSERT INTO name_details(id, name, type, n_copy)
                            VALUES(?, ?, ?, ?)""", (new_id, name, type_, n_copy))
                con.commit()
                con.close()
                self.update_table()
            if n_copy_cnt:
                imgs = "й"
                if n_copy_cnt % 10 == 1:
                    imgs = "е"
                if 2 <= n_copy_cnt % 10 <= 4:
                    imgs = "я"
                QMessageBox.warning(self, 'Предупреждение',
                                    f'С такими же именами в базе данных {n_copy_cnt} изображени{imgs}.')

    def delete_image(self, id_):
        btn = QMessageBox.warning(
            self,
            "Предупреждение",
            "Вы хотите удалить выбранное изображение из базы данных?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if btn == QMessageBox.StandardButton.Yes:
            con = sqlite3.connect("app_data.db")
            cur = con.cursor()
            cur.execute("""DELETE FROM images WHERE id = ?""", (id_,))
            cur.execute("""DELETE FROM name_details WHERE id = ?""", (id_,))
            con.commit()
            con.close()
            self.update_table()

    def delete_all(self):
        btn = QMessageBox.warning(self, "Предупреждение",
                                  "Вы хотите удалить все данные из базы данных безвозвратно?",
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if btn == QMessageBox.StandardButton.Yes:
            con = sqlite3.connect("app_data.db")
            cur = con.cursor()
            cur.execute("""DELETE FROM images""")
            cur.execute("""DELETE FROM name_details""")
            con.commit()
            con.close()
            self.update_table()

    def save_csv_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить как", "", "CSV files (*.csv);;All files (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline='', encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=';')

                headers = [self.table_img.horizontalHeaderItem(i).text()
                           for i in range(self.table_img.columnCount())]
                writer.writerow(headers)

                for i in range(self.table_img.rowCount()):
                    row = []
                    for j in range(self.table_img.columnCount()):
                        it = self.table_img.item(i, j)
                        text = "" if it is None else it.text()
                        if j == 4 and text:
                            text = f'="{text}"'
                        row.append(text)
                    writer.writerow(row)
        except PermissionError:
            QMessageBox.critical(self, "Ошибка",
                                 "Не удалось перезаписать файл. Закройте его в другой программе и повторите попытку.")

    def view_features(self, id_):
        self.features = Features(id_)
        self.features.show()

    def view_img(self, row):
        id_ = self.table_img.item(row, 0).text()
        self.OpenedImg = OpenedImg(id_, self)
        self.OpenedImg.show()

    def open_redactor(self, id_):
        self.redactor = Redactor(id_, self)
        self.redactor.show()


class Features(QWidget):
    def __init__(self, id_):
        super().__init__()
        uic.loadUi('features.ui', self)
        self.setWindowTitle('Свойства')
        self.id_ = id_
        con = sqlite3.connect("app_data.db")
        cur = con.cursor()
        s = cur.execute("""SELECT name, type, n_copy FROM name_details
        WHERE id = ?""", (id_,)).fetchone()
        con.close()
        if s:
            name, type_, n_copy = s
            if n_copy == 0:
                n_copy = "оригинал"
            else:
                n_copy = f"{n_copy}-ая копия"
            self.label_name.setText(name)
            self.label_type.setText(type_)
            self.label_n_copy.setText(str(n_copy))
            self.label_name.adjustSize()
            self.label_name.resize(self.label_name.width(), 31)
            new_width = self.label_name.x() + self.label_name.width() + 20
            if new_width > self.width():
                self.resize(new_width, self.height())
        self.setFixedSize(self.size())


class OpenedImg(QWidget):
    def __init__(self, id_, main=None):
        super().__init__()
        uic.loadUi('OpenedImg.ui', self)
        self.setFixedSize(360, 430)
        self.id_ = id_
        self.main = main
        self.features = None
        self.Redactor = None

        self.btn_features.clicked.connect(self.view_features)
        self.btn_delete.clicked.connect(self.del_image)
        self.btn_redact.clicked.connect(self.open_redactor)

        con = sqlite3.connect("app_data.db")
        cur = con.cursor()
        path, full_name = cur.execute("""SELECT path, full_name FROM images
                        WHERE id = ?""", (id_,)).fetchone()
        file_path = f"{path}/{full_name}"
        if not os.path.exists(file_path):
            s = cur.execute("""SELECT name, type FROM name_details WHERE id = ?""", (id_,)).fetchone()
            if s:
                file_path = f"{path}/{s[0]}.{s[1]}"
        con.close()

        self.orig_image = QImage(file_path)
        self.curr_image = QImage(self.orig_image)

        self.pixmap = QPixmap(file_path)

        self.image_label = QLabel(self)
        self.image_label.setGeometry(10, 10, self.width(), self.height())
        self.image_label.resize(round(self.width() * 0.7), round(self.height() * 0.7))
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        x = (self.width() - self.image_label.width()) // 2
        y = ((self.height() - 30) - self.image_label.height()) // 2
        self.image_label.move(x, y)

        self.display()

    def view_features(self):
        self.features = Features(self.id_)
        self.features.show()

    def open_redactor(self):
        self.Redactor = Redactor(self.id_, self.main)
        self.Redactor.show()
        self.close()

    def display(self):
        if not self.curr_image.isNull():
            pixmap = QPixmap.fromImage(self.curr_image)
            scaled_pixmap = pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)

    def del_image(self):
        if self.main:
            self.main.delete_image(self.id_)
            con = sqlite3.connect("app_data.db")
            cur = con.cursor()
            exists = cur.execute("""SELECT 1 FROM images
            WHERE id = ?""", (self.id_,)).fetchone()
            con.close()
            if not exists:
                self.close()


class Redactor(QWidget):
    def __init__(self, id_, main=None):
        super().__init__()
        uic.loadUi('Redactor.ui', self)
        self.setWindowTitle('Редактор')
        self.setFixedSize(770, 540)
        self.id_ = id_
        self.main = main

        self.mode = None
        self.drawing = False
        self.start_point = None
        self.last_point = None
        self.preview_image = None

        con = sqlite3.connect("app_data.db")
        cur = con.cursor()
        path, full_name = cur.execute("""SELECT path, full_name FROM images
                                WHERE id = ?""", (id_,)).fetchone()
        file_path = f"{path}/{full_name}"
        if not os.path.exists(file_path):
            s = cur.execute("""SELECT name, type FROM name_details WHERE id = ?""", (id_,)).fetchone()
            if s:
                file_path = f"{path}/{s[0]}.{s[1]}"
        con.close()

        self.file_path = file_path
        self.orig_image = QImage(self.file_path)
        self.curr_image = QImage(self.orig_image)

        self.image_label = QLabel(self)
        self.image_label.resize(round(self.width() * 0.8), round(self.height() * 0.8))
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        x = (self.width() - self.image_label.width()) // 2
        y = ((self.height() - 65) - self.image_label.height()) // 2
        self.image_label.move(x, y)

        self.display()

        self.btn_l_90.clicked.connect(self.rotate_left)
        self.btn_r_90.clicked.connect(self.rotate_right)
        self.btn_brush.clicked.connect(lambda: self.set_mode('brush'))
        self.btn_rubber.clicked.connect(lambda: self.set_mode('rubber'))
        self.btn_obrez.clicked.connect(lambda: self.set_mode('obrez'))
        self.btn_save.clicked.connect(self.save_image)
        self.btn_color.clicked.connect(self.choose_color)
        self.btn_shir.clicked.connect(self.choose_width)

        self.brush_color = QColor(Qt.GlobalColor.red)
        self.btn_color.setStyleSheet(f"background-color: red;")
        self.brush_width = 15

    def set_mode(self, mode):
        self.mode = mode

    def display(self, img=None):
        target = img if img is not None else self.curr_image
        if not target.isNull():
            pixmap = QPixmap.fromImage(target)
            scaled_pixmap = pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)

    def rotate_left(self):
        self.curr_image = self.curr_image.transformed(QTransform().rotate(-90))
        self.display()

    def rotate_right(self):
        self.curr_image = self.curr_image.transformed(QTransform().rotate(90))
        self.display()

    def get_img_pos(self, pos):
        pixmap = self.image_label.pixmap()
        if not pixmap or pixmap.isNull() or self.curr_image.isNull():
            return None
        img_pos = self.image_label.mapFromParent(pos)
        offset_x = (self.image_label.width() - pixmap.width()) // 2
        offset_y = (self.image_label.height() - pixmap.height()) // 2

        img_x = img_pos.x() - offset_x
        img_y = img_pos.y() - offset_y

        if 0 <= img_x <= pixmap.width() and 0 <= img_y <= pixmap.height():
            x = round(img_x * self.curr_image.width() / pixmap.width())
            y = round(img_y * self.curr_image.height() / pixmap.height())
            return QPoint(x, y)
        return None

    def choose_color(self):
        color = QColorDialog.getColor(self.brush_color, self, "Выберите цвет")
        if color.isValid():
            self.brush_color = color
            self.btn_color.setStyleSheet(f"background-color: {color.name()};")

    def choose_width(self):
        width, ok = QInputDialog.getInt(
            self, "Ширина линии", "Введите толщину (от 1 до 50):",
            value=self.brush_width, min=1, max=50
        )
        if ok:
            self.brush_width = width

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.mode:
            pt = self.get_img_pos(event.pos())
            if pt:
                self.drawing = True
                self.start_point = pt
                self.last_point = pt
                self.preview_image = self.curr_image.copy()

    def mouseMoveEvent(self, event):
        if self.drawing and self.mode:
            pt = self.get_img_pos(event.pos())
            if not pt:
                return

            if self.mode in ('brush', 'rubber'):
                painter = QPainter(self.curr_image)
                color = Qt.GlobalColor.white if self.mode == 'rubber' else self.brush_color
                painter.setPen(QPen(color, self.brush_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(self.last_point, pt)
                painter.end()
                self.last_point = pt
                self.display()

            elif self.mode == 'obrez':
                preview = self.preview_image.copy()
                painter = QPainter(preview)
                painter.setPen(QPen(Qt.GlobalColor.white, 2, Qt.PenStyle.DashLine))
                painter.drawRect(QRect(self.start_point, pt).normalized())
                painter.end()
                self.display(preview)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drawing:
            self.drawing = False
            pt = self.get_img_pos(event.pos())
            if not pt:
                self.display()
                return

            elif self.mode == 'obrez':
                rect = QRect(self.start_point, pt).normalized()
                if rect.width() > 5 and rect.height() > 5:
                    self.curr_image = self.curr_image.copy(rect)
                self.display()

    def save_image(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить изображение", self.file_path, "Изображения (*.png *.jpg *.webp *.jpeg)"
        )
        if path:
            self.curr_image.save(path)
            if os.path.normpath(path) != os.path.normpath(self.file_path) and self.main:
                self.main.add_image([path])
                self.file_path = path
            QMessageBox.information(self, "Успех", "Изображение сохранено!")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = Main()
    ex.show()
    sys.exit(app.exec())
