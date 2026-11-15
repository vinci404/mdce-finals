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
  let previewUrl = null;

  if (!fileInput || !emptyPreview || !pdfPreview || !imagePreview) return;

  fileInput.addEventListener("change", () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    pdfPreview.hidden = true;
    imagePreview.hidden = true;
    imagePreview.removeAttribute("src");

    const file = fileInput.files && fileInput.files[0];
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

  window.addEventListener("pagehide", () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  });
});
