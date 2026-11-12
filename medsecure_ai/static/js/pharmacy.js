(function () {
  const btn = document.getElementById("findPharmacyBtn");
  if (!btn) return;
  const msg = document.getElementById("locMsg"), res = document.getElementById("locResult");
  function fail(text) { msg.classList.remove("d-none"); msg.querySelector("p").textContent = text; res.classList.add("d-none"); }
  btn.addEventListener("click", () => {
    msg.classList.add("d-none");
    if (!navigator.geolocation) { fail("Location is not supported in this browser. Use the search link below."); return; }
    btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Finding your location...';
    navigator.geolocation.getCurrentPosition(p => {
      const lat = p.coords.latitude, lng = p.coords.longitude, d = 0.01;
      document.getElementById("osmMap").src = "https://www.openstreetmap.org/export/embed.html?bbox=" +
        [lng - d, lat - d, lng + d, lat + d].join("%2C") + "&layer=mapnik&marker=" + lat + "%2C" + lng;
      document.getElementById("mapsLink").href = "https://www.google.com/maps/search/pharmacy/@" + lat + "," + lng + ",15z";
      res.classList.remove("d-none");
      btn.disabled = false; btn.innerHTML = '<i class="bi bi-geo-alt"></i> Find Nearby Pharmacy';
    }, err => {
      btn.disabled = false; btn.innerHTML = '<i class="bi bi-geo-alt"></i> Find Nearby Pharmacy';
      fail(err.code === 1 ? "Location permission was denied. You can still use the search link below."
         : err.code === 3 ? "Finding your location took too long. Please try again."
         : "Your location is not available right now. Use the search link below.");
    }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 });
  });
})();
