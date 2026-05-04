# pdf-print2pdf

把 PDF 重新寫出成新的 PDF 檔。可指定單一 PDF，或指定資料夾批次處理所有 PDF；批次處理時會排除已產生的 `p-*.pdf`，避免把自己的輸出再重複處理。

此工具使用 PyMuPDF 重新儲存 PDF，適合用來重新產生、清理、正規化與壓縮 PDF。它不是透過系統印表機驅動程式列印，因此不需要另外安裝 Ghostscript。

## 需求

- Python 3.10 或更新版本
- PyMuPDF

安裝依賴套件：

```powershell
python -m pip install -r requirements.txt
```

## 使用方式

```powershell
python .\pdf_print2pdf.py <來源 PDF 或來源資料夾> [輸出 PDF 或輸出資料夾]
```

Windows 也可以直接執行：

```powershell
.\pdf_print2pdf.py <來源 PDF 或來源資料夾> [輸出 PDF 或輸出資料夾]
```

若直接執行時出現 PyMuPDF 未安裝，但 `python -m pip install -r requirements.txt` 顯示已安裝，代表 `.py` 檔案關聯使用了另一個 Python。此時請改用 `python .\pdf_print2pdf.py ...`，或依錯誤訊息中的 `Python executable` 路徑安裝套件。

### 單一 PDF

輸出到同資料夾，檔名加上 `p-` 前綴：

```powershell
python .\pdf_print2pdf.py .\input.pdf
```

會產生：

```text
.\p-input.pdf
```

指定輸出檔名：

```powershell
python .\pdf_print2pdf.py .\input.pdf .\output.pdf
```

指定輸出資料夾：

```powershell
python .\pdf_print2pdf.py .\input.pdf .\out
```

會產生：

```text
.\out\p-input.pdf
```

### 資料夾批次處理

處理資料夾中的所有 PDF，但排除 `p-*.pdf`：

```powershell
python .\pdf_print2pdf.py .\pdfs
```

輸出會放在原資料夾，檔名為 `p-原檔名.pdf`。

指定輸出資料夾：

```powershell
python .\pdf_print2pdf.py .\pdfs .\out
```

### 其他選項

覆蓋已存在的輸出檔：

```powershell
python .\pdf_print2pdf.py .\pdfs .\out --overwrite
```

遞迴讀取來源資料夾：

```powershell
python .\pdf_print2pdf.py .\pdfs .\out --recursive
```

## 行為說明

- 來源是 PDF 檔時，只處理該檔。
- 來源是資料夾時，預設只處理第一層的 `*.pdf`。
- 來源是資料夾時會排除檔名符合 `p-*.pdf` 的 PDF。
- 未指定輸出時，輸出到來源 PDF 所在資料夾。
- 輸出路徑若以 `.pdf` 結尾，視為輸出檔名，只能搭配單一來源 PDF 使用。
- 輸出路徑若不是 `.pdf`，或已存在且是資料夾，視為輸出資料夾。
- 預設不覆蓋既有輸出檔；需要覆蓋請加上 `--overwrite`。
- PDF 會透過 PyMuPDF 重新儲存，並啟用清理、垃圾回收與壓縮選項。
