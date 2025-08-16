# extrae-tel-pdf

Herramienta de consola para Windows que:

1. Lee el PDF indicado.
2. Extrae el teléfono de **República Dominicana** ubicado en la **esquina superior derecha**, justo después del texto **“Número asignado:”**.
3. Imprime el teléfono en **stdout** como **solo dígitos** (sin espacios, paréntesis, guiones ni “+”).
4. Crea una copia del PDF con nombre **`<solo_digitos>.pdf`** en el mismo directorio (sobrescribe si existe).

> Soporta prefijo +1 opcional y los códigos de área RD **809 / 829 / 849**.

---

## Ejecución (binario)

Descomprime el release y verifica esta estructura:

```
extrae_tel_pdf_vX.Y.Z.exe
tessdata/
  eng.traineddata
  spa.traineddata
tesseract/            (incluido en el ZIP del release)
  tesseract.exe
  *.dll
```

Ejemplo:

```powershell
.\extrae_tel_pdf_vX.Y.Z.exe EJ_TEL_IMAGE.pdf
```

Salida esperada (stdout):

```
8095551234
```

Se generará/actualizará también el archivo:

```
.\8095551234.pdf
```

---

## Requisitos

* **No necesitas instalar nada** si usas el ZIP del release (incluye `tesseract/` y `tessdata/`).
* Si compilas por tu cuenta y **no** incluyes `tesseract/`, debes tener **Tesseract OCR** instalado y en el `PATH`.

---

## Códigos de salida

| Código | Significado                |
| -----: | -------------------------- |
|      0 | Éxito                      |
|      1 | Error general / OCR        |
|      2 | No se encontró el teléfono |
|      3 | Error al copiar el PDF     |

---

## Solución de problemas

* **“tesseract is not installed or it's not in your PATH”**
  Asegúrate de tener la carpeta `tesseract/` junto al `.exe` (del release) o instala Tesseract en el sistema.

* **No se imprime ningún número**
  Verifica que en el PDF el texto **“Número asignado:”** esté realmente en la **esquina superior derecha**, y que el número esté a continuación. Si el PDF es escaneado de baja calidad, intenta con una versión de mayor resolución.

* **Modelos de idioma**
  Deben existir `tessdata/eng.traineddata` y `tessdata/spa.traineddata` junto al `.exe`.

---

## Compilación local (opcional)

Con **Miniconda**:

```powershell
conda create -n extrae_tel_pdf python=3.11 -y
conda activate extrae_tel_pdf

pip install --upgrade pip
pip install -r requirements.txt pyinstaller

# (Opcional) instalar tesseract para pruebas locales
# conda install -c conda-forge tesseract -y

pyinstaller --onefile --name extrae_tel_pdf extrae_tel_pdf_ocr.py

# Copia al lado del exe:
#  - la carpeta tessdata/ con eng.traineddata y spa.traineddata
#  - (opcional) la carpeta tesseract/ con tesseract.exe y DLLs
```

---

## Detalles de extracción

* Se procesa la **primera página** y se recorta la **esquina superior derecha** para el OCR.
* Se busca la cadena **“Número asignado:”** (tolerante a acentos) y, a continuación, se detecta el número con formato RD.
* El número se normaliza a **10 dígitos** (se descarta un posible `+1`).

---

## Verificación de integridad (release)

Cada release incluye `*.zip` y su `*.zip.sha256`. Para verificar:

```powershell
Get-FileHash -Algorithm SHA256 .\extrae_tel_pdf_vX.Y.Z.zip
# compara con el contenido de extrae_tel_pdf_vX.Y.Z.zip.sha256
```

---

## Licencia

Este proyecto se distribuye bajo la **licencia MIT**. Consulta el archivo [LICENSE](LICENSE) para más detalles.
