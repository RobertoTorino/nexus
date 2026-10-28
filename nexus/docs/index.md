---
template: home.html
hide:
  - navigation
  - toc
---
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

<section class="home-hero" markdown>
<a class="home-hero__play" href="videos/nexus.mp4" title="Play the Nexus video">
<img class="home-hero__icon" src="images/nexus-hero.webp" alt="The Nexus icon">
</a>
<div class="home-hero__text" markdown>
# Nexus { .home-hero__lead }
<p class="home-hero__claim">One home for the suites.</p>
<p class="home-hero__stage"><strong>Beta</strong> Nexus is in active development: features and layout may still change between releases.</p>
</div>
<div class="home-video" hidden>
<button class="home-video__close" type="button" aria-label="Close the video">×</button>
<video class="home-video__player" controls playsinline preload="metadata" poster="images/nexus-hero.webp">
<source src="videos/nexus.mp4" type="video/mp4">
Your browser cannot play this video; <a href="videos/nexus.mp4">download it</a> instead.
</video>
</div>
</section>

<section class="home-section home-section--dark" markdown>
<div class="home-section__inner" markdown>
## The name

A nexus is like a hub, the center every part leads back to.  
Nexus is where the suites connect: one repository holding every suite, the code they share, and the rules they’re built by.

</div>
</section>

<section class="home-section" markdown>
<div class="home-section__inner" markdown>
## The structure

<div class="home-grid" markdown>
<div class="home-card" markdown>
#### :material-file-tree: Nexus

The repository. It holds the suites, the shared code, the tools that test and [release](releases.md) them, and this
page.

</div>
<div class="home-card" markdown>
#### :material-view-grid: A suite

Apps for one operating system on one kind of device. A portal installs, opens, updates and removes them. Each suite
has its own wiki.

</div>
<div class="home-card" markdown>
#### :material-application: An app

One tool with one job. Each app has its own version, changelog and releases, and installs through its suite's
portal. A test app that gets to know the device is always installed and listed first.

</div>
</div>

</div>
</section>

<section class="home-section home-section--dark" markdown>
<div class="home-section__inner" markdown>
## How they relate

Every suite is built the same way: the same layout for each app, the same window, the same portal, and shared code
that ships with every app, so each app runs on the code it was tested with.

What differs is the device and the operating system. Each suite's apps read what its hardware reports and use what
its system offers, so an app made for one device is not copied one to one to another. The same kind of app on
each device gives results you can compare.

</div>
</section>

<section class="home-section" markdown>
<div class="home-section__inner" markdown>
## The suites

<div class="home-grid" markdown>
<div class="home-card" markdown>
#### :material-chip: BC250 Bazzite Suite

Tools for the AMD BC-250 running Bazzite: diagnostics, tuning, unlocks, gaming and the living room.
[Its wiki](bc250-bazzite-suite/).

</div>
<div class="home-card" markdown>
#### :material-controller: Windows Portable Suite

Tools for Windows 10/11 running on portable gaming devices, made for a small screen held in the hands, touch and a
controller. [Its wiki](windows-portable-suite/).

</div>
</div>

</div>
</section>

<section class="home-section home-section--accent" markdown>
<div class="home-section__inner" markdown>
## Get started

Pick the suite for your device: its wiki says how to install its portal, which installs every app of the suite. The
Nexus index, GitHub's latest release, names the newest portal of each suite.

[:material-download: Nexus index](https://github.com/RobertoTorino/nexus/releases/latest){ .md-button .md-button--primary }
[BC250 Bazzite Suite](bc250-bazzite-suite/){ .md-button }
[Windows Portable Suite](windows-portable-suite/){ .md-button }
</div>
</section>

<section class="home-section home-faq" markdown>
<div class="home-section__inner" markdown>
## License

GPL-3.0-or-later, the code of every suite on [GitHub](https://github.com/RobertoTorino/nexus). An app with a license
of its own says so in its suite's wiki, and each app has its own `LICENSE`.


</div>
</section>
