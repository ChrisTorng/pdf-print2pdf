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

## PDF 解密工具：pdf_unlock.py

原有的 `pdf_print2pdf.py` 保持不變：仍負責重寫、清理與壓縮 PDF，預設輸出 `p-原檔名.pdf`。
新增的 `pdf_unlock.py` 是**獨立 CLI**，專門處理 PDF 解密，預設輸出 `d-原檔名.pdf`。
兩者共用原本的資料夾搜尋、輸出位置與防覆寫機制；**解密不執行 Print to PDF 的清理與壓縮**。

### 支援範圍

- 未加密 PDF：逐位元組直接複製，不重新寫出 PDF 結構。
- 已知正確密碼：使用 PyMuPDF 移除加密，不套用原有 Print to PDF 的最佳化參數。
- 部分 MuPDF 1.28.5 前產生的弱金鑰 AES-256 R6/AESV3 文件：使用內建 Python 演算法復原。
- 受影響的 Foxit R6/AESV3 或 R7/AESV4 文件：選用 V12 原作者的 Rust CLI。
- 正常安全產生的加密金鑰不在無密碼解密的支援範圍。

### Windows PowerShell

~~~powershell
python -m pip install -r requirements-unlock.txt

# 單檔，輸出 d-input.pdf
python .\pdf_unlock.py .\input.pdf

# 指定輸出 PDF
python .\pdf_unlock.py .\input.pdf .\output.pdf

# 資料夾批次；預設排除 p-*.pdf 與 d-*.pdf
python .\pdf_unlock.py .\pdfs

# 指定目的地、遞迴、覆寫
python .\pdf_unlock.py .\pdfs .\out --recursive --overwrite

# 已知密碼
python .\pdf_unlock.py .\input.pdf --password "YOUR_PASSWORD"

# 只檢查 PDF 加密特徵，不產生輸出
python .\pdf_unlock.py .\input.pdf --inspect
~~~

輸出檔如已存在，預設拒絕覆蓋；僅在指定 `--overwrite` 時允許。原始輸入永不覆蓋。
輸入 PDF 的 `Producer`、`Creator` 可能是加密欄位，不能單靠品牌字串確定加密引擎。
程式以 `/R`、`/CFM` 選擇相容候選方法，並驗證解密金鑰；必要時可以用 `--engine mupdf` 或 `--engine foxit` 指定偵錯方式。
已知密碼可加 `--inspect --password "YOUR_PASSWORD"` 讀取更多文件資訊。

### Foxit Rust CLI（選用）

作者提供可直接編譯的 CLI：https://github.com/v12-security/pocs/tree/main/pdf_decryptors/foxitpdf
先安裝 Rust（https://rustup.rs/），再執行：

~~~powershell
git clone https://github.com/v12-security/pocs.git ..\pocs
Push-Location ..\pocs\pdf_decryptors\foxitpdf
cargo build --release
Pop-Location
python .\pdf_unlock.py .\input.pdf
~~~

預設尋找相鄰的 `..\pocs\pdf_decryptors\foxitpdf\target\release\foxit-decrypt.exe`，其他位置可用 `--foxit-exe` 指定：

~~~powershell
python .\pdf_unlock.py .\input.pdf --foxit-exe "D:\Tools\foxit-decrypt.exe"
~~~

解密工具不額外執行 Print to PDF 的壓縮，但解密後重新儲存可能影響數位簽章或特殊 PDF 結構；請保留原件。
MuPDF 暫時存取密碼每次由安全亂數產生，不寫死在原始碼中。

### 測試

~~~powershell
python -m unittest discover -s tests -v
~~~

參考：https://v12.sh/blog/the-case-of-the-9bit-aes-key
