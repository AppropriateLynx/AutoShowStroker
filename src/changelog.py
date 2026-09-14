"""User-facing changelog, shown in the in-app "What's New" popup.

Every `feat:` (or critical `fix:`) version bump must add an entry here describing what's
new, in the app's own flirty/teasing voice for the end user - not a commit-log dump. Write
entries as a short suggestive lead sentence, then an inline HTML `<ul><li>` bullet list of
the real features, then a one-line closing hook - WhatsNewDialog renders the body as rich
text, so the markup shows up as actual bullets. See CLAUDE.md's "Versioning & Releases"
section.
"""

CHANGELOG = {
    "0.1.0": (
        "GoonerApp's first release is here to edge you properly."
        "<ul>"
        "<li>Randomized slideshow playback that syncs perfectly to a fully configurable "
        "Strokemeter</li>"
        "<li>Multilingual teasing callouts in English, German, and French, whispering you "
        "along the whole way</li>"
        "<li>Difficulty ramping that slowly tightens the screws as your session builds</li>"
        "<li>A full climax announcement system - real, ruined, denied, and the occasional "
        "cruel fake-out</li>"
        "</ul>"
        "Load up your folder and see how long you actually last."
    ),
    "0.2.0": (
        "GoonerApp got dressed up for you - dark, neon, and dripping in pink."
        "<ul>"
        "<li>A full cyber-erotic theme glow-up: deep purple backgrounds, glowing pink "
        "accents, curves everywhere</li>"
        "<li>Settings reorganized into tabs so nothing falls off your screen mid-session</li>"
        "<li>A one-click \"Reset to defaults\" on every tab, no fumbling required</li>"
        "<li>This very \"What's New\" popup, so you never miss what's new to play with</li>"
        "</ul>"
        "Go on, undress the new Settings menu and see for yourself."
    ),
    "0.3.0": (
        "GoonerApp hands you the sticks - build your own rhythm from scratch."
        "<ul>"
        "<li>A brand-new Pattern Editor: drag each step's bar to set how long it lingers, "
        "1 (longest) to 4 (shortest)</li>"
        "<li>A dedicated Beat/Pause button per step, so a pause can tease just as long "
        "(or as short) as you want it to</li>"
        "<li>Live preview playback, so you can hear exactly what you're building before "
        "you commit to it</li>"
        "<li>Your own patterns sit right alongside the built-in ones in the Active Rhythms "
        "list, ready to be picked at random</li>"
        "</ul>"
        "Head to Settings > Beat &amp; Rhythm > Manage Custom Patterns and compose your own edge."
    ),
    "0.4.0": (
        "GoonerApp now remembers every session you've ever survived - and isn't shy about it."
        "<ul>"
        "<li>Break a personal best and the end-of-session recap throws up a glowing "
        "\"New Personal Record\" card for it, right on the spot</li>"
        "<li>A new Statistics menu holds your full history: sessions played, all-time bests, "
        "and a trend chart charting how your stamina climbs over time</li>"
        "<li>Fakeouts now count toward something - survive enough of them and that's a record "
        "too</li>"
        "</ul>"
        "Check the Statistics menu after your next session and watch the line go up."
    ),
    "0.5.0": (
        "GoonerApp finally lets you window-shop before you commit."
        "<ul>"
        "<li>A brand-new folder picker replaces the plain Windows dialog - stack up as many "
        "folders as you want in one go, each weighted equally in the preview</li>"
        "<li>A live thumbnail grid teases a random sample before you hit Start, so you're "
        "never loading in blind again</li>"
        "<li>Gifs already play right in the grid, and videos can too - flip on \"Animate "
        "video clips\" for a looping 5-second peek at each one</li>"
        "<li>Your last-used folders are remembered, ready the next time you open the picker</li>"
        "</ul>"
        "Open the folder picker and see what's waiting for you before you dive in."
    ),
    "0.5.1": (
        "GoonerApp wants to stay close, and finally tells you how it all works."
        "<ul>"
        "<li>A new Socials menu with a one-click Join Discord, so the community is never "
        "more than a click away</li>"
        "<li>A brand-new Guide under Help - a plain-language breakdown of what the beat "
        "pattern numbers actually mean, straight from the source</li>"
        "<li>The Guide also walks you through adding a new callout language, no Python "
        "required</li>"
        "<li>Built to grow - more guide topics will slot in right alongside these as the app "
        "gets bigger</li>"
        "</ul>"
        "Pop open Help &gt; Guide and finally learn what makes this thing tick."
    ),
    "0.6.0": (
        "GoonerApp levels up on three fronts at once - discoverability, control, and trust."
        "<ul>"
        "<li>Every keyboard shortcut is finally documented - a new Keyboard Shortcuts tab in "
        "the Guide, plus the README, list them all in one place</li>"
        "<li>Two shortcuts that were missing outright: Ctrl+O opens/changes your folder, and "
        "F1 pops the Guide open instantly</li>"
        "<li>A new Mute button (or just hit M) silences the beat sound and video audio "
        "together, instantly</li>"
        "<li>Panic Mode - tap Space and the window minimizes and goes silent in one move, no "
        "questions asked, no session lost</li>"
        "<li>A new Privacy tab in the Guide (and right at the top of the README) spells it "
        "out plainly: everything runs 100% locally, nothing ever phones home</li>"
        "</ul>"
        "Pop open Help &gt; Guide - it's got a lot more to say for itself now."
    ),
    "0.6.1": (
        "GoonerApp finally makes an entrance instead of just barging in."
        "<ul>"
        "<li>A glowing logo fade-in greets you on launch now - the neon mark easing in, "
        "holding for a beat, then dissolving away right before your session starts</li>"
        "<li>Not in the mood for a tease before the tease? A new \"Show startup splash "
        "animation\" toggle in Settings &gt; Playback turns it off instantly</li>"
        "</ul>"
        "Watch it once, then decide if you want the intro every time."
    ),
    "0.6.2": (
        "GoonerApp now taunts you the moment a record is actually within reach."
        "<ul>"
        "<li>A glowing badge flashes up in the corner once you're closing in on a personal "
        "best - total beats, duration, active speed, or fakeouts survived, whichever you're "
        "nearest to breaking</li>"
        "<li>Cross the line and it flips straight to \"New Record!\" without waiting for the "
        "recap screen</li>"
        "<li>Stays out of your way otherwise - no badge, no clutter, until you're actually "
        "close</li>"
        "<li>A new \"Show live personal-record chase\" toggle in Settings &gt; Playback turns "
        "it off if you'd rather be surprised at the end</li>"
        "</ul>"
        "Keep playing - it'll let you know when it's time to get excited."
    ),
    "0.6.3": (
        "GoonerApp can finally tell you when it's grown - if you ask nicely first."
        "<ul>"
        "<li>A new \"Check for Updates...\" action under Help asks GitHub, once, whether a "
        "newer version exists</li>"
        "<li>Always asks permission first - a clear warning pops up every single time before "
        "anything gets sent, no exceptions</li>"
        "<li>Nothing automatic, nothing silent - no background checks, no Settings toggle to "
        "forget about, just a button you press when you're curious</li>"
        "<li>Finds one? A one-click link straight to the Releases page</li>"
        "</ul>"
        "Pop open Help when you're curious - it'll only ever speak up if you ask."
    ),
    "0.6.4": (
        "GoonerApp finally lets your own words into the mix, no code required."
        "<ul>"
        "<li>Settings &gt; Callouts &gt; Manage Custom Phrase Files lets you point the app at "
        "your own phrase file, anywhere on your machine - same simple format the built-in "
        "ones already use</li>"
        "<li>Pick the language it's for, add it, and it's live immediately - no restart</li>"
        "<li>Your phrases join the built-in ones in the mix, never replace them</li>"
        "<li>Load as many files as you like, and drop any of them just as easily</li>"
        "</ul>"
        "Write it once, save it anywhere, and let GoonerApp read it back to you."
    ),
    "0.7.0": (
        "GoonerApp's biggest single day yet, all bundled into one real release."
        "<ul>"
        "<li>A glowing splash greets you on launch now - the neon mark easing in before every "
        "session</li>"
        "<li>A live record-chase badge flashes up the moment you're closing in on (or "
        "breaking) a personal best</li>"
        "<li>Help &gt; Check for Updates - ask GitHub, on your terms, whether a newer version "
        "exists</li>"
        "<li>Settings &gt; Callouts &gt; Manage Custom Phrase Files - load your own teasing "
        "lines from anywhere on your machine, no code required</li>"
        "</ul>"
        "Four new tricks in one build - go find all of them."
    ),
    "0.7.1": (
        "GoonerApp now keeps its own quiet count of exactly how long you've been at it."
        "<ul>"
        "<li>A small glowing clock ticks away in the top-left the whole session, wall-clock "
        "time, pauses included</li>"
        "<li>A new \"Show session timer\" toggle in Settings &gt; Playback hides it if you'd "
        "rather not watch the numbers climb</li>"
        "<li>A new Guide tab, \"On-Screen Display\", finally explains everything glowing on "
        "your screen - the timer and the record-chase badge alike</li>"
        "</ul>"
        "However long you think you've lasted, now you'll actually know."
    ),
    "0.8.0": (
        "The Strokemeter stopped just blinking at you - now it shows you what's coming."
        "<ul>"
        "<li>A whole new animated Strokemeter: beats glide in from the right and land on the "
        "hit line at the exact moment you hear them, so you feel every one approaching before "
        "it takes you</li>"
        "<li>A rhythm's silent steps read as the gaps between notes, so you can see the shape "
        "of what's being done to you instead of guessing at it</li>"
        "<li>Every change of pattern announces itself with a sweep of light across the track</li>"
        "<li>Your session history and custom patterns moved out of the Windows registry into "
        "proper files in your AppData folder - they carry themselves over on first launch, "
        "nothing is lost, and your history is no longer capped at 200 sessions</li>"
        "</ul>"
        "Watch them come at you now. See how long you keep up."
    ),
    "0.8.1": (
        "No more safewords for the app - it takes whatever you do to it and keeps going."
        "<ul>"
        "<li>Unticking every last rhythm no longer kills the app mid-session - and it won't "
        "let you leave yourself with nothing to stroke to in the first place</li>"
        "<li>Setting a pause minimum above its maximum used to end things very abruptly. "
        "Settings now tells you off instead, for every min/max pair</li>"
        "<li>A hand-edited or damaged custom pattern file gets its bad entries quietly "
        "skipped rather than taking the whole session down with it</li>"
        "<li>And when something does go wrong deep in the rhythm engine, the Strokemeter "
        "no longer seizes up on you</li>"
        "</ul>"
        "Go on. Try to break it."
    ),
    "0.8.2": (
        "Whatever you get up to in here is nobody's business but yours - so now you can "
        "see every trace of it, and wipe any of it."
        "<ul>"
        "<li>New under Help &gt; Privacy &amp; Data: exactly where everything about you is "
        "kept, a button straight to the folder, and deletion by category - wipe the "
        "folders you've been using without losing what you achieved in them</li>"
        "<li>The folders you pick no longer linger in the Windows registry, where nothing "
        "could reach them. They sit with the rest of your data now, deletable</li>"
        "<li>Your data also moved off the roaming half of your profile, so a work laptop "
        "can't quietly copy your history somewhere you'd rather it didn't</li>"
        "<li>Turning the beat or video volume down finally survives a restart</li>"
        "<li>And on a fresh install the callouts actually talk to you, instead of silently "
        "ignoring you until you found the right dial</li>"
        "</ul>"
        "Everything moves itself over on first launch. Nothing lost - unless you ask for it."
    ),
    "0.8.3": (
        "Less waiting, more edging. Everything between you and the next picture got quicker."
        "<ul>"
        "<li>Picking your folders no longer locks up for seconds while it previews your "
        "clips - it takes the frames it can get and moves on instead of making you wait</li>"
        "<li>Scanning a big collection is several times faster, so it stops keeping you "
        "waiting before it starts keeping you waiting</li>"
        "<li>Large photos land noticeably sooner, and the Strokemeter no longer stutters "
        "when a heavy one does</li>"
        "<li>The startup screen now loads the app behind itself instead of before itself, "
        "so you get to your folders sooner</li>"
        "<li>And the beat keeps stricter time - no more sloppy milliseconds where you were "
        "promised none</li>"
        "</ul>"
        "Nothing left in your way. Go on."
    ),
    "0.8.4": (
        "When you say stop, it stops. When it can't give you what you asked for, it moves on."
        "<ul>"
        "<li>Ending a session now actually ends it - a video used to keep playing behind "
        "your stats, and then quietly start the whole slideshow up again without you</li>"
        "<li>A clip your machine can't decode no longer leaves you staring at a black "
        "screen until you take over. It gives up on that one and gives you the next</li>"
        "<li>Being denied can't cut short a session you already started again</li>"
        "<li>The pattern editor's preview stops clicking away in the background once you "
        "close it with Escape</li>"
        "<li>And a damaged install no longer refuses to open at all - it tells you what's "
        "missing and lets you use everything else</li>"
        "</ul>"
        "Fewer surprises. Unless you asked for those."
    ),
    "0.8.5": (
        "The small stuff, tidied. You'll mostly notice it by nothing going wrong."
        "<ul>"
        "<li>Walking out mid-session now counts. Closing the window used to throw the "
        "whole thing away - no time on the clock, no record, as if you'd never started</li>"
        "<li>No more ghost timer sitting on the start screen counting up from a session "
        "that ended long ago</li>"
        "<li>Saving your settings mid-pause no longer yanks you out of it with a new "
        "rhythm you never get to feel</li>"
        "<li>The pause-chance dial responds to its arrows again, instead of politely "
        "snapping back to where it was</li>"
        "<li>A session too short to settle on a favourite rhythm says so, rather than "
        "telling you your favourite was 'None'</li>"
        "<li>And the update check now tells you exactly what it hands to GitHub, down to "
        "the one line that identifies the app</li>"
        "</ul>"
        "Nothing dramatic. Just less in your way."
    ),
    "0.8.6": (
        "For the times it misbehaves and you want to know why - strictly on your terms."
        "<ul>"
        "<li>New in Help &gt; Privacy &amp; Data: \"Write a diagnostic log file\". It notes "
        "what the app is doing, so a problem you report can actually be traced</li>"
        "<li><b>Off unless you switch it on.</b> A log is a record of when you used this, "
        "and that's yours to hand over or not</li>"
        "<li>You decide how much it writes down - everything, problems only, or errors "
        "only</li>"
        "<li>It never writes down which folders you play from. A file that refuses to load "
        "gets named, nothing else does</li>"
        "<li>It sits with the rest of your data and wipes on its own under Help &gt; "
        "Privacy &amp; Data, without touching anything you've earned</li>"
        "</ul>"
        "Leave it off. Unless you want a witness."
    ),
}


def parse_version(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def entries_since(last_seen_version: str, current_version: str, changelog: dict | None = None) -> dict:
    changelog = CHANGELOG if changelog is None else changelog
    last_seen = parse_version(last_seen_version) if last_seen_version else (0,)
    current = parse_version(current_version)
    return {
        version: text
        for version, text in changelog.items()
        if last_seen < parse_version(version) <= current
    }
