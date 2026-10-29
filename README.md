# pdf-print2pdf

把 PDF 重新寫出成新的 PDF 檔，並自動檢查加密格式、選擇支援的解密引擎。可指定單一 PDF，或指定資料夾批次處理所有 PDF；批次處理時會排除已產生的 `p-*.pdf`，避免把自己的輸出再重複處理。

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


## PDF 加密自動辨識與解密（統一入口：pdf_print2pdf.py）

沿用原本的 `pdf_print2pdf.py` 作為**唯一需要記住的 CLI**。`pdf_unlock.py` 是處理引擎路由的 Python 模組，也保留直接執行的相容入口。原有單檔、資料夾、批次輸出、p- 前綴、`--recursive` 與 `--overwrite` 全部保留。

支援：
- 未加密文件：直接重新輸出。
- 已知 PDF 使用者或擁有者密碼：由 PyMuPDF 解密後輸出。
- MuPDF 1.28.5 以前所產生、符合弱金鑰特徵的 AES-256 revision-6 PDF：由本專案的 Python 復原程式處理，不需要 mutool 或 Rust。
- 受影響的 Foxit AESV3/AESV4 PDF：使用 V12 提供的 Rust CLI（需另行編譯）。
- 不支援直接解開所有一般安全加密的 PDF。

### PDF 來源辨識原則

- `--inspect` 只讀取 PDF，加密修訂版 `/R`、加密方法 `/CFM` 及可讀的 `Producer`、`Creator`，不會輸出新檔；`--inspect --password` 可顯示正確解密後的原始產生器資訊。
- `/Producer`、`/Creator`、XMP 等中繼資料在受密碼保護的 PDF 裡往往無法事先讀取；有值也可能被修改或只描述最近一次寫入軟體。**不能僅靠這些欄位確認是哪個加密實作。**
- `R6 / AESV3`：先試 MuPDF 弱亂數金鑰驗證，再試 V12 Foxit Rust 解密器（若已編譯）；若可讀到 Foxit／PDFium 產生器中繼資料，則調整候選順序。
- `R7 / AESV4`：只考慮已知 Foxit Rust 解密器。
- 其他加密格式：已知密碼才嘗試一般解密，否則回報不支援。
- **完成解密後**會讀取並報告 Producer／Creator；成功解密的方法表示符合某一金鑰弱點，*不保證*是該品牌軟體製作的文件。
- 不會下載或自動安裝外部二進位檔。Foxit 工具如未編譯，會提示安裝方法；未安裝不會被誤報為已解密。

~~~powershell
# 只檢查文件格式與可能的解密方法
python .\pdf_print2pdf.py .\input.pdf --inspect

# 如果知道密碼，可解開中繼資料以查 Producer/Creator
python .\pdf_print2pdf.py .\input.pdf --inspect --password "YOUR_PASSWORD"

# 不用指定引擎，自動辨識、驗證並輸出
python .\pdf_print2pdf.py .\input.pdf

# 自動批次處理
python .\pdf_print2pdf.py .\pdfs .\out --recursive
~~~

### 安裝及基本使用（Windows PowerShell）

~~~powershell
python -m pip install -r requirements.txt

# 單檔：預設輸出 p-input.pdf
python .\pdf_print2pdf.py .\input.pdf

# 指定輸出檔
python .\pdf_print2pdf.py .\input.pdf .\output.pdf

# 已知密碼（不需要弱金鑰漏洞）
python .\pdf_print2pdf.py .\input.pdf --password "YOUR_PASSWORD" --engine password

# 僅使用內建的 MuPDF 弱金鑰還原方法
python .\pdf_print2pdf.py .\input.pdf --engine mupdf

# 資料夾批次處理：輸出到 out，排除 p-*.pdf
python .\pdf_print2pdf.py .\pdfs .\out --recursive --overwrite
~~~

預設 --engine auto：先使用提供的密碼，再試 MuPDF 弱金鑰；若仍失敗，就在找到已編譯的 Foxit CLI 時執行 Foxit 復原。原始輸入不會被覆寫。若無法解密會顯示錯誤，不會產生假裝成功的檔案。

### Foxit Rust CLI（選用）

作者提供的是可直接編譯並執行的 CLI，不必自行開發 Rust 專案：

https://github.com/v12-security/pocs/tree/main/pdf_decryptors/foxitpdf

先安裝 Rust（https://rustup.rs/）。在本專案目錄執行：

~~~powershell
git clone https://github.com/v12-security/pocs.git ..\pocs
Push-Location ..\pocs\pdf_decryptors\foxitpdf
cargo build --release
Pop-Location

python .\pdf_print2pdf.py .\input.pdf --engine foxit
~~~

預設搜尋相鄰的 ..\pocs\pdf_decryptors\foxitpdf\target\release\foxit-decrypt.exe，也可指定其他位置：

~~~powershell
python .\pdf_print2pdf.py .\input.pdf --engine foxit --foxit-exe "D:\Tools\foxit-decrypt.exe"
python .\pdf_print2pdf.py .\input.pdf --engine foxit --pocs "D:\Tools\pocs"
~~~

不透過本專案也可以直接執行作者工具（從 foxitpdf 目錄）：

~~~powershell
.\target\release\foxit-decrypt.exe .\protected.pdf .\decrypted.pdf
~~~

### 範圍與限制

- 研究原文：https://v12.sh/blog/the-case-of-the-9bit-aes-key
- 作者的 MuPDF Python PoC：https://github.com/v12-security/pocs/tree/main/pdf_decryptors/mupdf
- MuPDF Python 復原程式依據公開的亂數弱點獨立實作，不需外部 mutool，並額外搜尋更多亂數串流偏移，以處理連續儲存的舊版 MuPDF。
- 支援 revision-6 AESV3 且使用一般十六進位 /Perms、/U、/UE 字典格式；不保證支援每種增量更新、物件壓縮或非標準加密結構。
- Foxit Rust 工具支援格式以原作者 README 為準，不保證每個 Foxit 版本均受同一缺陷影響。
- 重新輸出可能影響原 PDF 的數位簽章、互動功能或內部結構；需保留簽章效力時請保留原件。
- 本專案不複製、再散布 V12 的 Rust PoC 原始碼，而是執行使用者自行編譯的官方程式。
- 請只處理自己擁有或取得授權的 PDF。

### 測試

~~~powershell
python -m unittest discover -s tests -v
~~~

使用 MuPDF 1.28.5 或更新版本時，端對端弱金鑰產生測試會略過。
