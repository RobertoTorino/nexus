<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Steam artwork from SteamGridDB

A game put in Steam (by PCSX2 Manager's **Update Steam**) has a cover in Steam's library and a banner on its page.
A PS2 disc brings no pictures in Steam's shapes, so the app draws them from its icon with the game's title. With
a SteamGridDB API key of your own, Update Steam looks each game up on [SteamGridDB](https://www.steamgriddb.com) by
its title and takes the pictures with the most votes instead.

## The key

The key is free. To get one:

1. Sign in on [SteamGridDB](https://www.steamgriddb.com) and open **Preferences** in your account.
2. Click the **API** tab at the top.
3. On the API page, click **Generate API Key**.
4. Copy the key.

Signed in, the API page is also at
[steamgriddb.com/profile/preferences/api](https://www.steamgriddb.com/profile/preferences/api).

Copy it in a browser on the device, then in PCSX2 Manager press **Steam artwork** on the Your games pane:

- **X Paste** puts the copied key in the field; a tap on the field lets you type it instead.
- **A Save** keeps it. **Y Remove key** takes it out again, on a second press.
- **B** goes back without saving.

It is one key for the whole suite: the other apps use it too. It is kept in
`%APPDATA%\windows-portable-suite\steamgriddb-key`, in your own user folder, and is sent only to SteamGridDB. Leave
it empty, or remove it, to look nothing up; the pictures found before stay in use.

## How a game is looked up

The next **Update Steam** looks up each game marked for Steam by its title, without tags such as `(USA)` or `[!]` from
a file name. It takes the game with exactly that name, else the first one SteamGridDB finds, and of each picture the
one with the most votes, leaving out pictures marked as adult, humor or epilepsy. A picture SteamGridDB does not have
stays drawn.

SteamGridDB's pictures are made by its users. Many redraw the game's art in Steam's style; few look like the box of
the console version, and a smaller game may have none. A game with a title that is not its name, or a name shared
with another game, may get the other game's pictures.

## Your own pictures

The app looks up a game once and keeps what it found in its covers folder,
`%LOCALAPPDATA%\windows-portable-suite\windows-portable-pcsx2\covers\`, so a later change to Steam takes the same
pictures, also offline. A picture you put there in place of one, under the same name, is taken the same way.
