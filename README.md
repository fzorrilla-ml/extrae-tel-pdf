# Extractor de teléfono para PDFs

Este repositorio contiene un pequeño proyecto en Python que permite extraer un
número de teléfono de República Dominicana a partir de la primera página de un
PDF y generar una copia del archivo con el número como nombre. El objetivo es
obtener un ejecutable Windows sin dependencias externas mediante GitHub
Actions.

## Funcionamiento del script

El script `extrae_tel_pdf_ocr.py` busca en la esquina superior derecha del PDF
el texto **“Número asignado:”** y extrae el número de teléfono que aparece a
continuación. Soporta documentos con texto nativo (usa pdfminer) y
documentos escaneados (usa PyMuPDF y Tesseract OCR). Una vez encontrado,
crea una copia del PDF original en la misma carpeta, nombrada únicamente con
los dígitos del teléfono y la extensión `.pdf` (p. ej. `DIGITOS.pdf`).

## Ejecución local

Para ejecutar el script como módulo de Python se requieren las siguientes
dependencias:

* Python 3.8 o superior.
* [pdfminer.six](https://pypi.org/project/pdfminer.six/) para extraer texto.
* [PyMuPDF](https://pypi.org/project/PyMuPDF/) para renderizar imágenes de
  PDFs escaneados.
* [pytesseract](https://pypi.org/project/pytesseract/) y Tesseract OCR.
* [Pillow](https://pypi.org/project/Pillow/) (se instala automáticamente con
  pytesseract).

Una vez instaladas, puede ejecutarse así:

```bash
python extrae_tel_pdf_ocr.py ruta/al/archivo.pdf
```

Si el teléfono se encuentra correctamente, se imprime por la salida estándar
solo el número y se crea la copia del PDF. El código de salida 0 indica
éxito. Consulte el código para más detalles.

## Compilación del ejecutable con GitHub Actions

El workflow definido en `.github/workflows/build.yml` crea un ejecutable
auto‑conteniḓ0 para Windows utilizando PyInstaller. Las principales fases
del workflow son:

1. **Instalación de dependencias:** instala Python 3.11, pdfminer.six,
   pymupdf, pytesseract, Pillow y PyInstaller.
2. **Instalación de Tesseract:** instala el binario de Tesseract mediante
   Chocolatey e incorpora los datos de entrenamiento en español.
3. **Preparación del directorio `vendor/tesseract`:** copia el contenido
   de la instalación de Tesseract a un directorio `vendor/tesseract`,
   que se incluirá dentro del ejecutable.
4. **Compilación:** ejecuta PyInstaller con la opción `--onefile` y
   `--add-data "vendor\\tesseract;tesseract"` para incluir la carpeta
   completa dentro del paquete.
5. **Publicación del artefacto:** sube el ejecutable generado
   (`extrae_tel_pdf.exe`) como artefacto descargable.

El objetivo de este pipeline es generar un `.exe` que pueda ejecutarse en
máquinas Windows sin necesidad de instalar Python ni Tesseract.

## Cómo utilizar este repositorio

1. Crea un repositorio nuevo en GitHub y sube los archivos de este
   proyecto (`extrae_tel_pdf_ocr.py`, el workflow y este README).
2. Asegúrate de tener habilitadas las GitHub Actions en tu repositorio.
3. Realiza un _push_ a la rama `main` o ejecuta manualmente el workflow
   mediante `workflow_dispatch` desde la interfaz de GitHub.
4. Una vez finalizado el workflow, encontrarás el ejecutable en la sección
   *Artifacts* del trabajo de Actions o podrás programar un release
   automático usando otras acciones si lo deseas.

## Licencia

Este proyecto se distribuye bajo la licencia MIT. Tesseract OCR se distribuye
bajo la licencia Apache 2.0; los datos de entrenamiento se descargan en
tiempo de ejecución a través del workflow.
