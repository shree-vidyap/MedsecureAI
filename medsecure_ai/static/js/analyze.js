(function () {
  const input = document.getElementById("imageInput");
  const img = document.getElementById("previewImg");
  const text = document.getElementById("dropText");
  const zone = document.getElementById("dropZone");
  const form = document.getElementById("uploadForm");
  if (!input) return;
  const OK = ["image/jpeg", "image/png"];

  function show(file) {
    if (!file) return;
    if (!OK.includes(file.type)) {
      alert("Unsupported file format. Please upload JPG, JPEG, or PNG.");
      input.value = ""; return;
    }
    img.src = URL.createObjectURL(file);
    img.classList.remove("d-none");
    text.classList.add("d-none");
  }
  input.addEventListener("change", () => show(input.files[0]));
  ["dragover", "dragenter"].forEach(e => zone.addEventListener(e, ev => { ev.preventDefault(); zone.classList.add("over"); }));
  ["dragleave", "drop"].forEach(e => zone.addEventListener(e, ev => { ev.preventDefault(); zone.classList.remove("over"); }));
  zone.addEventListener("drop", ev => {
    if (ev.dataTransfer.files.length) { input.files = ev.dataTransfer.files; show(input.files[0]); }
  });
  form.addEventListener("submit", ev => {
    if (!input.files.length) { ev.preventDefault(); alert("Please upload a medicine image."); return; }
    document.getElementById("btnText").classList.add("d-none");
    document.getElementById("btnSpin").classList.remove("d-none");
    document.getElementById("analyzeBtn").disabled = true;
  });
})();
