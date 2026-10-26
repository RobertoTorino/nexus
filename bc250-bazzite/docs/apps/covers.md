<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Covers from SteamGridDB

The game managers put your games in Steam, so they start from there, also from Steam's Big Picture Mode (Game Mode
on a handheld). Steam shows every game with four pictures:

| Picture | Where Steam shows it |
|---|---|
| Cover (600 × 900) | the tiles in the library, and in Recent Games all but the first |
| Wide picture (920 × 430) | the first tile in Recent Games, the game you played last |
| Banner | across the top of the game's page |
| Logo | on the banner |

A game rarely brings these itself, so the managers draw them. With a SteamGridDB API key they take them from
[SteamGridDB](https://www.steamgriddb.com) instead, a site where players share artwork for Steam.

| Managers | What comes from SteamGridDB |
|---|---|
| shadPS4, RPCS3, Vita3K, PPSSPP | the cover. The banner, wide picture and logo stay the game's own pictures. |
| PCSX2, Xenia | all four. Their games bring no pictures, so the app draws them from its own icon and the game's title. |

## The key

The key is free. To get one:

1. Sign in on [SteamGridDB](https://www.steamgriddb.com) and open **Preferences** in your account.
2. Click the **API** tab at the top.
3. On the API page, click **Generate API Key**.
4. Copy the key.

Signed in, the API page is also at
[steamgriddb.com/profile/preferences/api](https://www.steamgriddb.com/profile/preferences/api).

In any of these managers press **Covers…** (in PCSX2 Manager **Steam artwork…**) and paste it. It is one key for the whole suite: the other managers use it too. It is kept in
`~/.config/bc250-bazzite-suite/steamgriddb-key`, which only you can read, and is sent only to SteamGridDB. Leave
it empty to look nothing up.

## How a game is looked up

The next **Update Game Mode** (in PCSX2 Manager and RPCS3 Manager **Update Steam**) looks up each ticked game by its title, without tags such as `(USA)` or `[!]` from a
file name. It takes the game with exactly that name, else the first one SteamGridDB finds, and of each picture the
one with the most votes, leaving out pictures marked as adult, humor or epilepsy. A picture SteamGridDB does not
have stays drawn.

SteamGridDB's pictures are made by its users. Many redraw the game's art in Steam's style; few look like the box of
the console version, and a smaller game may have none. A game with a title that is not its name, or a name shared
with another game, may get the other game's pictures.

## Your own pictures

The app looks up a game once and keeps what it found in its covers folder,
`~/.local/share/<app>/covers`, so a later change to Steam takes the same pictures, also offline. The files are named
like Steam's own: the game's ID (its title ID or serial, as the app's list shows it) and `p` for the cover, nothing
for the wide picture, `_hero` for the banner and `_logo` for the logo: `CUSA01234p.png`, `CUSA01234.png`,
`CUSA01234_hero.png`, `CUSA01234_logo.png`. To use a picture of your own, a box scan for example, put it there under
that name, in place of the one there; the next change to Steam takes it. A game without an ID is kept under a name
made from its title.

A picture chosen in Steam's own settings (the game's page, the gear, **Properties**, **Customization**) is replaced
by the next **Update Game Mode** (**Update Steam**).

To look a game up again, delete its `<ID>.done` file in the covers folder.
