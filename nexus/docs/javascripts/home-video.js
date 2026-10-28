/* SPDX-License-Identifier: GPL-3.0-or-later */
/* The Nexus icon on the home page plays the Nexus video (owner, 28-10-2026): a click opens the player over the
   page; Escape, the close button or a click beside the player put it away and pause it. Without this script the
   icon is a link to the video file, which the browser plays by itself. */
(function () {
  function init() {
    var link = document.querySelector(".home-hero__play");
    var box = document.querySelector(".home-video");
    if (!link || !box) { return; }
    var video = box.querySelector("video");
    var close = box.querySelector(".home-video__close");
    function open(event) {
      event.preventDefault();
      box.hidden = false;
      close.focus();
      video.play();
    }
    function hide() {
      if (box.hidden) { return; }
      video.pause();
      box.hidden = true;
      link.focus();
    }
    link.addEventListener("click", open);
    close.addEventListener("click", hide);
    box.addEventListener("click", function (event) { if (event.target === box) { hide(); } });
    document.addEventListener("keydown", function (event) { if (event.key === "Escape") { hide(); } });
  }
  if (window.document$) {                 /* Material's page observable: also after instant navigation */
    window.document$.subscribe(init);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
