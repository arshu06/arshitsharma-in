# How the build works

You add a file. Everything else updates itself.

## The three things you now edit

**`_partials/header.html`** the masthead, tagline and nav. One copy. Change it
here and all pages get it on the next push.

**`_partials/footer.html`** the footer. Same.

**`_partials/head.html`** the charset, viewport, favicon and stylesheet lines.

`{{ROOT}}` becomes `../` on pages inside a folder and nothing at the root.
`{{CUR:notes}}` becomes `aria-current="page"` on whichever page you are on.

## Adding a review or a note

Copy an existing one, change the prose, and change the metadata block at the
top of the `<head>`:

    <meta name="x-kind"   content="review">      review or note
    <meta name="x-date"   content="2026-09-04">  YYYY-MM-DD, sorts newest first
    <meta name="x-title"  content="Place, Area"> the card heading
    <meta name="x-kicker" content="One line.">   the card sub
    <meta name="x-score"  content="3 in 4">      optional, the bold bit
    <meta name="x-meta"   content="23 / 30 ...">  the grey line
    <meta name="x-thumb"  content="images/x.jpg"> optional
    <meta name="x-draft"  content="true">        optional, hides it everywhere

Push it. The front page, the food reviews index and the notes index all pick
it up. You never touch `index.html` again.

**Metadata is plain text.** No quotes, no tags. The build will refuse if you
put HTML in there, because a quote inside an attribute truncates the card and
you would not notice for a week.

## Where the cards come from

    <!--#cards:note:1-->      newest 1 note
    <!--#cards:review:3-->    newest 3 reviews
    <!--#cards:review:all-->  every review

Change the number to change how many appear. That is the only edit the front
page ever needs again.

## Running it

Nothing to install. Push to `main` and the Action runs, rebuilds, and commits
the result back. Takes about thirty seconds.

To run it by hand: Actions tab, "Build site", Run workflow.

## When it fails

The commit gets a red cross and nothing is written. Click into Actions to see
which file and what is wrong. Cloudflare keeps serving the last good version,
so a failed build never takes the site down.

It fails on: missing metadata, a date in the wrong format, an image path that
does not exist, a link pointing at a file that is not there, wrong-case
filenames, and missing markers.

That last list is every gotcha in your handoff doc, now caught before it ships
instead of three days later on mobile data.

## The markers

    <!--#head-->    ... <!--#/head-->
    <!--#header-->  ... <!--#/header-->
    <!--#footer-->  ... <!--#/footer-->
    <!--#cards:...--> ... <!--#/cards-->

The build only ever rewrites the text between a pair. Everything outside is
copied through untouched. It cannot eat a paragraph you wrote.

Do not delete the markers.
