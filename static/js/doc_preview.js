document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("select[data-other]").forEach((select) => {
    const otherInput = document.getElementById(select.dataset.other);
    if (!otherInput) return;

    const syncOtherInput = () => {
      const showOther = select.value === "Other";
      otherInput.hidden = !showOther;
      otherInput.required = showOther;
    };

    select.addEventListener("change", syncOtherInput);
    syncOtherInput();
  });

  const fileInput = document.getElementById("doc-file");
  const emptyPreview = document.getElementById("doc-preview-empty");
  const pdfPreview = document.getElementById("doc-pdf-preview");
  const imagePreview = document.getElementById("doc-image-preview");
  const ocrPanel = document.querySelector(".doc-ocr-panel");
  const ocrButton = document.getElementById("doc-ocr-button");
  const ocrResult = document.getElementById("doc-ocr-result");
  const ocrStatus = document.getElementById("doc-ocr-status");
  let previewUrl = null;

  if (!fileInput || !emptyPreview || !pdfPreview || !imagePreview) return;

  fileInput.addEventListener("change", () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    pdfPreview.hidden = true;
    imagePreview.hidden = true;
    imagePreview.removeAttribute("src");

    const file = fileInput.files && fileInput.files[0];
    if (ocrButton) ocrButton.disabled = !file;
    if (ocrResult) ocrResult.value = "";
    if (ocrStatus) ocrStatus.textContent = "";
    if (!file) {
      emptyPreview.textContent = "Choose a PDF or image file to preview it here.";
      emptyPreview.hidden = false;
      return;
    }

    const extension = file.name.split(".").pop().toLowerCase();
    previewUrl = URL.createObjectURL(file);

    if (extension === "pdf") {
      pdfPreview.src = previewUrl;
      pdfPreview.hidden = false;
      emptyPreview.hidden = true;
    } else if (["png", "jpg", "jpeg", "webp"].includes(extension)) {
      imagePreview.src = previewUrl;
      imagePreview.hidden = false;
      emptyPreview.hidden = true;
    } else {
      URL.revokeObjectURL(previewUrl);
      previewUrl = null;
      emptyPreview.textContent = "This file type cannot be previewed here. Choose a PDF or image file.";
      emptyPreview.hidden = false;
    }
  });

  if (ocrButton && ocrPanel && ocrResult && ocrStatus) {
    ocrButton.addEventListener("click", async () => {
      const file = fileInput.files && fileInput.files[0];
      if (!file) return;

      const payload = new FormData();
      payload.append("file", file);
      ocrButton.disabled = true;
      ocrResult.value = "";
      ocrStatus.textContent = "Reading document… this can take a little while.";

      try {
        const response = await fetch(ocrPanel.dataset.ocrUrl, {
          method: "POST",
          body: payload,
          credentials: "same-origin"
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "OCR could not read this file.");

        ocrResult.value = result.text || "";
        if (result.text) {
          ocrStatus.textContent = "Text recognized. Please review it; OCR can make mistakes.";
        } else {
          ocrStatus.textContent = "No readable text was found. The preview is still available.";
        }
      } catch (error) {
        ocrStatus.textContent = error.message || "Could not read the file. Please try again.";
      } finally {
        ocrButton.disabled = false;
      }
    });
  }

  window.addEventListener("pagehide", () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  });
});
