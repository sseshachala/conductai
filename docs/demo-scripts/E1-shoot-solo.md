# E1 — Shoot Script (Solo, Live Person)

**Runtime:** ~3:00 · **You:** on camera + screen share · **Companion:** `E1-the-140-dollar-ticket.md`

This is a **teleprompter script**, not a produced-video script. One person (you), talking to camera, cutting to screen when the line calls for it. No character voices. No VO. Read it at conversational pace.

Setup before you hit record:
- Sierra ticket mock loaded in one tab (Figma prototype).
- ConductAI open in another tab. Left tab: `/theguard/activity` (empty or filtered to today). Right tab: `/theguard/spend`.
- Teleprompter on phone above the webcam. Eyes on the lens.
- One take per section. Don't chase perfection. Descript will save you.

Screen cues in **[brackets]**. Everything else you say.

---

## 0:00 — 0:20 · Hook

**[Camera. You.]**

I want to show you one ticket at a company we'll call PH.

They run four million support tickets a year. This one is going to cost them a hundred and forty dollars.

Not because the AI can't fix it. The AI knows the fix. It just isn't allowed to run it.

That gap is what this episode is about.

**[Pause. Half beat.]**

---

## 0:20 — 0:50 · The pain

**[Cut to screen: Sierra ticket #48213 loaded. Diagnosis panel visible.]**

Here's the ticket. Store 7 in Boulder. POS laptop won't boot after last night's Windows patch.

Sierra reads the boot log. Spots the corrupt BCD entry. Knows the fix. One script, thirty seconds.

PH has three ways to close this ticket. **[Back to camera.]**

Onsite tech to the store: about a hundred and forty dollars.

A remote screenshare with a human: thirty-five.

Sierra runs the script herself: fifteen cents.

Guess which one runs today? The truck. Because if Sierra writes to a POS terminal in the middle of Black Friday and bricks the register, someone's on a call with Northwind's CIO on Monday.

So every fix routes through a human. The AI tier is worth nothing.

---

## 0:50 — 1:20 · The gap

**[Camera. You.]**

The problem isn't Sierra's capability. Sierra is capable. The problem is authority.

Sierra needs a place to ask, before she fires, "am I allowed to run this action, on this device, for this customer, right now."

That place is Guard.

**[Optional screen: simple diagram — Sierra box, Guard diamond, remediation API box.]**

Two ways in. Sierra can call `guard_check` before she acts. Cooperative. Or if she skips it, the remediation API sits behind our proxy and the same rule fires. Hard boundary.

Either way, same answer. Same receipt.

---

## 1:20 — 2:15 · Walkthrough

**[Cut to screen: Sierra proposes remediation.]**

Watch the round trip.

Sierra proposes `remediation.run` with the boot repair script, targeted at store7-pos-04, on Northwind's account.

**[Click. `guard_check` response appears.]**

Guard blocks it. Northwind's contract is retail-hardened. No unattended writes on POS-class devices. And Guard doesn't just say no. It suggests the next move: propose the fix for review, one-click approval.

The receipt line, right there: cost avoided, a hundred thirty-nine dollars and eighty-five cents.

**[Sierra re-plans. Second `guard_check`. ALLOWED.]**

Sierra re-plans. Queues the script for the on-call tech. Tech's phone buzzes. One tap. Script runs. Register boots.

Total cost of this ticket: fifteen cents of compute, plus thirty seconds of a human hand.

**[Cut to `/theguard/activity`. Two rows visible.]**

And here's what the operator sees. Two rows. First one blocked, cost avoided a hundred and thirty-five bucks. Second one allowed. Sierra tried, Guard corrected her, Guard let her land. One receipt.

---

## 2:15 — 2:45 · The number

**[Cut to `/theguard/spend`. Cost Avoided card. Number animates 139 → 1,458 → 18,791.]**

This is one ticket. This is one day.

Multiply by four million tickets a year, and the AI tier is finally worth what PH paid for it. Because it's finally allowed to work.

**[Back to camera.]**

That is the shape of every real win in this space. The story is never "we bought smarter models." The story is "we finally gave the model a place to ask permission, and got a receipt on the way out."

---

## 2:45 — 3:00 · Tease

**[Camera. Slight smile.]**

Next episode: Northwind's compliance team emails Sarah and asks to see the audit log.

We'll show you what that looks like.

**[Card overlay: "E2 — The Customer Asks for the Log."]**

---

## Delivery notes for you

- Sarah and Marcus are gone. You are the voice of the whole thing. Don't ventriloquize the customer. Say "PH" and "Sierra," not "I."
- Pace: conversational. Not TED-talk, not tutorial-speedrun. Aim ~145 words/min. This script is ~440 words, lands right at 3 min.
- Kill filler on the read. If you catch yourself saying "so," "basically," "essentially," don't self-correct in the take. Descript will strip them.
- The two beats that need silence: after "worth nothing" (0:50) and after "one receipt" (2:14). Don't rush past them.
- If you flub a line, restart the paragraph, not the section. Easier to cut in Descript.
- Screen cuts happen in edit. On camera, just say the line and imagine the screen there. Look at the lens, not your monitor.

## Shot checklist

1. Talking-head takes for 0:00, 0:20 (transitions), 0:50, 2:15, 2:30 (close), 2:45 (tease). One take each, second take if flubbed.
2. Screen recording: Sierra ticket load → diagnose → propose → block → re-plan → allowed → activity feed. One continuous screen capture is fine, cut in edit.
3. Screen recording: `/theguard/spend` card animation. If the card isn't built yet, mock as Descript overlay.
4. Assemble in Descript. Cut filler, add captions, add lower-third callouts for numbers ($140, $35, ¢¢, $139.85).
