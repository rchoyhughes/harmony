# Harmony

**Chaos ends here. I challenge myself to build Harmony.**

## Why

It began with a mistake. One I didn't mean to make, but one that hurt someone I care about, regardless of my intention.

I accidentally double-booked myself, *again*.

Not because I didn't care, but because I live in chaos.

Texts. Links. Threads. Flights. Emails. Tickets. Half-formed plans. All commitments, nothing actionable.

A close friend felt like an afterthought because of my chaos. My best friend told me it was too much of a commitment to organize her chaos, that she felt shame of her plans slipping through the cracks.

**Chaos ends here.**

Harmony is a project meant to fight the overwhelm, the friction, the shame in wallowing in chaos, the feeling of forgetfulness, the fear of letting our friends down.

## Mission

Bring an end to chaos, gently.

Empower those living with guilt with capability.

Reduce the friction required to show up for the people we love.

## What Harmony will do

Harmony is not a calendar, nor a productivity system, nor a life coach. It's something much simpler.

**Harmony takes the disorganized threads of being human and weaves them into something clear.**

- Screenshot of a text saying “dinner next Thursday around 7?”

- Screenshot of an email with concert info

- A picture of a flyer posted in a group chat

- A link to a reservation or event page

Send it to Harmony.

Harmony quietly reads it, interprets it, and returns later with a gentle notification:

*“I think this is Dinner with Tim, on Tuesday, December 2 at 7pm at Garden Carver. Want to add it to your calendar?”*

Confirm or edit it with one tap, and add it to your calendar. **No friction, no forgetting.**

## Principles

1. Harmony does not judge.

    People who forget things already feel shame. Harmony is gentle and affirming.

2. Harmony deletes friction.

    If adding an event takes more than a few taps, then Harmony has failed.

3. Harmony respects privacy.

    Screenshots do not leave the device. Only the relevant text is sent to be parsed.

4. Harmony captures now and clarifies later.

    Real people do not organize in the moment. Harmony offloads that burden.

5. Harmony embraces fuzziness.

    "Next Thursday." "7-ish?" "After I land." Humans do not live in rigid blocks of time, and Harmony understands this.

6. Harmony is a tool, not a coach.

    Harmony does not try to be a figure of authority, a life coach, an assistant, or a friend. It just helps.

## How it works

The pipeline is simple:

1. Share a screenshot with Harmony in the iOS Share Sheet.

2. On-device OCR extracts the text privately.

3. A lightweight LLM interprets the text and turns it into structured event details.

4. Harmony sends a push notification to confirm the event details.

5. The user confirms, edits, or dismisses.

6. Harmony adds it to your calendar.

**That's it.**

Harmony is tiny, simple, helpful, and human.

## Technical Overview

- iOS Share Extension to accept screenshots

- Vision OCR for private on-device text extraction

- LLM to parse text and transform it to structured JSON

- Local storage for pending event suggestions

- Local notifications to confirm/add events

- EventKit to write events to the user’s calendar

This will evolve over time, but Harmony's soul will remain this intake pipeline.

## Roadmap

Phase 0: Python Prototype **(current)**

- turn text into event JSON

- turn screenshot into text

- no UI, no iOS

Phase 1: iOS Skeleton

- share extension

- dummy suggestion list

- calendar write

Phase 2: OCR and parsing

- Vision integration (OCR)

- LLM endpoint

- suggestion creation

Phase 3: Notification flow

- *“Looks like [event], add to calendar?”*

Phase 4: Polish and Trust

- gentle tone

- minimal UI

- privacy features

- reliability

## A Personal Note

Harmony is not a startup idea.

Harmony is a promise I'm making to myself.

Harmony is a gift for my friends to help them end chaos.

If Harmony helps my friends even once, then Harmony has done its job.

Harmony is for those who live in constant mental noise. For the friends we love and never want to hurt on accident. For the parts of ourselves that we've come to terms with but want to change.

**Chaos ends here. Chaos ends in Harmony.**
