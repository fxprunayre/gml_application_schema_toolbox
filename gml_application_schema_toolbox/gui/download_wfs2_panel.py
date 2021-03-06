# -*- coding: utf-8 -*-

import os
import owslib_hacks
import owslib

from owslib.wfs import WebFeatureService
from owslib.feature.wfs200 import WFSCapabilitiesReader

from tempfile import NamedTemporaryFile

import logging

from qgis.core import QgsCoordinateTransform, QgsCoordinateReferenceSystem
from qgis.utils import iface

from qgis.PyQt.QtCore import (
    Qt, pyqtSignal, pyqtSlot,
    QSettings,
    QUrl, QFile, QIODevice)
# from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QMessageBox, QFileDialog, QListWidgetItem
from qgis.PyQt.QtXml import QDomDocument
from qgis.PyQt import uic

from gml_application_schema_toolbox.core.logging import log
from gml_application_schema_toolbox.core.proxy import qgis_proxy_settings
from gml_application_schema_toolbox.core.settings import settings

from .xml_dialog import XmlDialog

WIDGET, BASE = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), '..', 'ui', 'download_wfs2_panel.ui'))

class DownloadWfs2Panel(BASE, WIDGET):

    file_downloaded = pyqtSignal(str)

    def __init__(self, parent=None):
        super(DownloadWfs2Panel, self).__init__(parent)
        self.setupUi(self)

        self.downloadProgressBar.setVisible(False)

        self.featureLimitBox.setValue(int(settings.value('default_maxfeatures')))
        self.uriComboBox.addItems(settings.value('wfs2_services') or [])
        self.uriComboBox.setCurrentText(settings.value('default_wfs2_service'))

    def wfs(self):
        uri = self.uriComboBox.currentText()
        with qgis_proxy_settings():
            return WebFeatureService(url=uri)

    @pyqtSlot()
    def on_getCapabilitiesButton_clicked(self):
        wfs = self.wfs()

        self.featureTypesListWidget.clear()
        for feature_type in list(wfs.contents):
            item = QListWidgetItem(feature_type)
            item.setData(Qt.UserRole, feature_type)
            self.featureTypesListWidget.addItem(item)

        self.featureTypesListWidget.sortItems()


        self.storedQueriesListWidget.clear()
        if hasattr(wfs, "storedqueries"):
            for stored_query in list(wfs.storedqueries):
                self.storedQueriesListWidget.addItem(stored_query.id)

        self.storedQueriesListWidget.sortItems()

    @pyqtSlot()
    def on_showCapabilitiesButton_clicked(self):
        XmlDialog(self, self.wfs().getcapabilities().read()).exec_()
        # url = WFSCapabilitiesReader().capabilities_url(self.uri())
        # QDesktopServices.openUrl(QUrl(url))

    @pyqtSlot()
    def on_outputPathButton_clicked(self):
        path, filter = QFileDialog.getSaveFileName(self,
            self.tr("Select output file"),
            self.outputPathLineEdit.text(),
            self.tr("GML Files (*.gml *.xml)"))
        if path:
            if os.path.splitext(path)[1] == '':
                path = '{}.gml'.format(path)
            self.outputPathLineEdit.setText(path)

    @pyqtSlot()
    def on_downloadButton_clicked(self):
        self.downloadProgressBar.setValue(0)
        self.downloadProgressBar.setVisible(True)
        self.setCursor(Qt.WaitCursor)
        try:
            if self.datasetsTabWidget.currentIndex() == 0:
                out = self.download()
            if self.datasetsTabWidget.currentIndex() == 1:
                out = self.download_stored_query()
        finally:
            self.downloadProgressBar.setVisible(False)
            self.unsetCursor()
        if out is not None:
            self.file_downloaded.emit(out)

    def selected_typenames(self):
        typenames = []
        for item in self.featureTypesListWidget.selectedItems():
            typenames.append(item.data(Qt.UserRole))
        return typenames

    def _get_bbox(self, wfs):
        """
        Get the selected bbox in the default CRS of the first selected layer.
        """
        default_crs_name = wfs.contents[self.selected_typenames()[0]].crsOptions[0]
        default_crs = QgsCoordinateReferenceSystem.fromOgcWmsCrs(str(default_crs_name))
        assert default_crs.isValid()
        transform = QgsCoordinateTransform(self.bboxWidget.crs(), default_crs)
        bbox = transform.transformBoundingBox(self.bboxWidget.rectangle())
        return [bbox.xMinimum(),
                bbox.yMinimum(),
                bbox.xMaximum(),
                bbox.yMaximum(),
                default_crs_name]

    def download(self):
        wfs = self.wfs()

        typenames = self.selected_typenames()
        if len(typenames) == 0:
            return

        params = {
            'typename': typenames,
            'maxfeatures': self.featureLimitBox.value(),
        }

        if self.bboxGroupBox.isChecked():
            if self.bboxWidget.value() == '':
                QMessageBox.warning(self,
                                    self.windowTitle(),
                                    "Extent is empty")
                return
            if not self.bboxWidget.isValid():
                QMessageBox.warning(self,
                                    self.windowTitle(),
                                    "Extent is invalid")
                return
            params['bbox'] = self._get_bbox(wfs)

        try:
            with qgis_proxy_settings():
                response = wfs.getfeature(**params)
        except owslib.util.ServiceException as e:
            QMessageBox.critical(self, 'ServiceException', str(e))
            return
        xml = response.read()

        doc = QDomDocument()
        if not doc.setContent(xml):
            return
        root = doc.documentElement()
        exception = root.firstChildElement('ows:Exception')
        if not exception.isNull():
            QMessageBox.critical(self,
                                 'ows:Exception',
                                 exception.text())
            return

        path = self.outputPathLineEdit.text()
        if path == '':
            with NamedTemporaryFile(mode="w+t", suffix='.gml', delete=False) as out:
                out.write(xml)
                path = out.name
        else:
            with open(path, 'w') as out:
                out.write(xml)

        return path

    def download_stored_query(self):
        pass
