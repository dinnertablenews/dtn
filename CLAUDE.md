# Dinner Table News

## The voice rule applies to everything

Every word written in this repository is in Dan's voice and carries no AI tells.
Everything means everything: the scripts in `post.json`, the website, the About page,
the walkthrough copy, README and PRD prose, commit messages, PR bodies. The post copy is
not a special case with looser rules elsewhere. It is one rule.

Two sources sit behind it. Dan's style analysis, taken from 110k words of his writing and
speech, says what the voice is. Wikipedia's "Signs of AI writing" says what to strip out.

## Dan's voice

- Open with a concrete fact, a scene, or a provocation. Never a thesis statement, never a
  warm-up. Arrive; don't clear your throat.
- Short to medium sentences. Active voice, subject-verb-object. Passive almost never.
- Build by accumulating specifics: numbers, names, dates, distances. Trust the reader to
  follow data without hand-holding, then name the stakes plainly once the specifics have
  earned it.
- An adjective does argumentative work or it comes out.
- Dry humour as an aside. It ventilates serious material. It never takes over.
- Name a weakness plainly when there is one. "I don't know" is an available answer.
- Reach for the particular before the general. Generalise from the anecdote, not toward it.
- Frameworks are tools for the reader, never a display. Wear them lightly.
- Flip the expected frame where the flip is true.
- Keep the sentences lean. Economy is the strength, not a constraint on it.

## The tells

Checked against Wikipedia's "Signs of AI writing". Do not write:

- **Rule of three for effect.** "adjective, adjective, adjective", or "short phrase, short
  phrase, and short phrase". Three real things in a real list are fine. A triad built for
  rhythm is not.
- **Negative parallelism.** "not just X but Y", "it's not X, it's Y", "X isn't about A,
  it's about B", "no A, no B, just C".
- **Trailing participle analysis.** "..., highlighting its significance", "..., reflecting
  a broader shift", "..., ensuring that", "..., contributing to".
- **Copula avoidance.** "serves as", "stands as", "represents", "boasts", "features",
  "offers", "refers to" where the word is *is* or *has*.
- **Significance and legacy claims.** "a testament to", "a pivotal moment", "a rich
  tapestry", "the evolving landscape", "left an indelible mark", "underscores the
  importance of", "marks a shift", "setting the stage for".
- **AI vocabulary.** delve, crucial, pivotal, key (adjective), robust, vibrant, intricate,
  meticulous, enduring, garner, foster, enhance, showcase, underscore, highlight (verb),
  align with, resonate with, valuable insights, groundbreaking, renowned, nestled, in the
  heart of, diverse array, commitment to.
- **Vague attribution.** "experts say", "observers have noted", "studies suggest", "it is
  widely regarded". Name the person or cut the claim. One source is one source.
- **Hedged wrap-ups.** "it's important to note", "worth noting", "in summary", "in
  conclusion", "overall".
- **The challenges formula.** "Despite these challenges, X continues to Y."
- **Em-dash chains.** One in a paragraph is a choice. Three is a tell, and a dash standing
  in for a comma, a colon or a parenthesis usually wants to be that instead.
- **Title case headings.** Sentence case.
- **Boldface for emphasis inside prose.**
- **A tidy moral in the last sentence.**

Write it, then read it back against this list. A sentence that survives only because it
sounds good comes out.

## Length

The "why it works" note on a post may not run longer than that post's summary. The reader
came for the news; the note about how to talk about it is the smaller of the two. `site.py`
fails the build with `WHY TOO LONG:` and names the post, the age band and the overage.

## The name

Always "Dinner Table News". Three words. Never "Dinnertable".
