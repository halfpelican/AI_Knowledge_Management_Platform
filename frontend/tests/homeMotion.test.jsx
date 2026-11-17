/**
 * The motion on PR #119's home page (NFR-16; WCAG 2.1 SC 2.2.2 Pause, Stop,
 * Hide, level A and so inside NFR-16's AA).
 *
 * SC 2.2.2: motion that starts automatically, lasts more than five seconds and
 * is presented in parallel with other content needs a way to pause, stop or hide
 * it. The home page's illustration has two animations beside the offer to sign
 * in, a blinking cursor and three floating icons, and #119 looped both forever.
 * They now stop within five seconds, so no control is needed, and they still
 * play, as #119 designed. A visitor who asks the system for less motion gets
 * none of it.
 *
 * jsdom applies no stylesheet and runs no animation, so the rules are read from
 * disk (tests/stylesheets.js) and matched against the rendered page: every
 * element a visitor's page holds, the shell's included.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { TEXT } from '../src/constants.js'
import { serveApi } from './fakeApi.js'
import { describe as name, resolve, rulesMatching, splitTopLevel } from './stylesheets.js'

const NOT_SIGNED_IN = { status: 401, body: { detail: 'Authentication credentials were not provided.' } }

/** SC 2.2.2's bound. */
const FIVE_SECONDS = 5000

const REDUCED_MOTION = /prefers-reduced-motion:\s*reduce/

const TIME = /^(-?\d*\.?\d+)(ms|s)$/
const PRODUCT = /^calc\(\s*(-?\d*\.?\d+)(ms|s)\s*\*\s*(\d*\.?\d+)\s*\)$/
const COUNT = /^\d*\.?\d+$/
const KEYWORDS = new Set([
  'ease',
  'linear',
  'ease-in',
  'ease-out',
  'ease-in-out',
  'step-start',
  'step-end',
  'normal',
  'reverse',
  'alternate',
  'alternate-reverse',
  'forwards',
  'backwards',
  'both',
  'running',
  'paused',
])

/** A time, `1s`, `600ms` or `calc(0.7s * 2)`, in milliseconds; null when the text is not one. */
function milliseconds(text) {
  const time = text.match(TIME)
  if (time) return Number.parseFloat(time[1]) * (time[2] === 's' ? 1000 : 1)
  const product = text.match(PRODUCT)
  if (product) return Number.parseFloat(product[1]) * (product[2] === 's' ? 1000 : 1) * Number.parseFloat(product[3])
  return null
}

function iterations(text) {
  return text === 'infinite' ? Infinity : Number.parseFloat(text)
}

/** An `animation` shorthand as one {name, duration, delay, count} per animation it lists. */
function parseShorthand(value) {
  return splitTopLevel(value, ',').map((single) => {
    const parts = splitTopLevel(single.replace(/\s+/g, ' '), ' ')
    const times = parts.map(milliseconds).filter((time) => time !== null)
    const count = parts.find((part) => part === 'infinite' || COUNT.test(part))
    const animationName = parts.find(
      (part) =>
        milliseconds(part) === null &&
        part !== 'infinite' &&
        !COUNT.test(part) &&
        !KEYWORDS.has(part) &&
        !/^(cubic-bezier|steps)\(/.test(part),
    )
    return {
      name: animationName ?? 'none',
      duration: times[0] ?? 0,
      delay: times[1] ?? 0,
      count: count === undefined ? 1 : iterations(count),
    }
  })
}

/** One declaration's say on an element's animation, as lists of the values it sets. */
function motionIn(declarations) {
  const motion = { names: [], durations: [], delays: [], counts: [] }
  for (const { property, value } of declarations) {
    const resolved = resolve(value).trim()
    const values = splitTopLevel(resolved, ',')
    if (property === 'animation') {
      for (const one of parseShorthand(resolved)) {
        motion.names.push(one.name)
        motion.durations.push(one.duration)
        motion.delays.push(one.delay)
        motion.counts.push(one.count)
      }
    } else if (property === 'animation-name') motion.names.push(...values)
    else if (property === 'animation-duration') motion.durations.push(...values.map(milliseconds))
    else if (property === 'animation-delay') motion.delays.push(...values.map(milliseconds))
    else if (property === 'animation-iteration-count') motion.counts.push(...values.map(iterations))
  }
  return motion
}

/**
 * What every rule matching `element` under conditions `admit` accepts says of its
 * animation. Conservative, as tests/stylesheets.js's hidingCauses is: every value
 * any matching rule sets is kept, so the longest delay, duration and count found
 * bound how long the element can move, whichever rule wins in the browser.
 */
function motionOf(element, admit) {
  const declarations = rulesMatching(element)
    .filter((rule) => admit(rule.media ?? ''))
    .flatMap((rule) => rule.declarations)
  return motionIn(declarations)
}

const outsideReducedMotion = (media) => !REDUCED_MOTION.test(media)

/** The elements that animate on the page as most visitors see it. */
function animatedElements() {
  return [...document.body.querySelectorAll('*')].filter((element) =>
    motionOf(element, outsideReducedMotion).names.some((animationName) => animationName !== 'none'),
  )
}

/** Whether a reduced-motion rule's declarations stop every animation on what it matches. */
function stopsMotion(declarations) {
  const motion = motionIn(declarations)
  if (motion.names.length > 0 && motion.names.every((animationName) => animationName === 'none')) return true
  // The global form some stylesheets use: every animation cut to one imperceptible
  // run. A duration alone is not enough: a loop of 0.01ms runs forever.
  return (
    motion.counts.length > 0 &&
    motion.counts.every(Number.isFinite) &&
    motion.durations.length > 0 &&
    motion.durations.every((duration) => duration !== null && duration <= 0.01)
  )
}

async function visitHome() {
  serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN })
  render(
    <MemoryRouter initialEntries={['/']}>
      <App />
    </MemoryRouter>,
  )
  await screen.findByRole('link', { name: TEXT.homeRegister })
}

describe('SC 2.2.2: the home page’s motion stops on its own, and not at all for a visitor who asks for less', () => {
  it('ends every animation within five seconds of the page opening, its delay counted, and still plays #119’s', async () => {
    await visitHome()
    const animated = animatedElements()

    // #119's motion is still there: the cursor blinks and each of the three icons floats.
    const designed = [
      document.querySelector('.home-visual__cursor'),
      ...document.querySelectorAll('.home-visual__icon'),
    ]
    expect(designed).toHaveLength(4)
    for (const element of designed) expect(animated, `${name(element)} no longer moves`).toContain(element)

    for (const element of animated) {
      const motion = motionOf(element, outsideReducedMotion)
      const label = name(element)
      // A shorthand with no count runs once, and parseShorthand records it as 1.
      const count = Math.max(1, ...motion.counts)
      const duration = Math.max(...motion.durations.filter((time) => time !== null))
      const delay = Math.max(0, ...motion.delays.filter((time) => time !== null))
      expect(Number.isFinite(count), `${label} loops forever`).toBe(true)
      expect(duration, `${label} has no duration, so it never plays`).toBeGreaterThan(0)
      expect(delay + duration * count, `${label} moves for ${delay + duration * count} ms`).toBeLessThanOrEqual(
        FIVE_SECONDS,
      )
    }
  })

  it('stops every one of them for a visitor whose system asks for reduced motion, and starts none', async () => {
    await visitHome()
    const animated = animatedElements()
    expect(animated.length).toBeGreaterThan(0)

    for (const element of animated) {
      const reduced = rulesMatching(element).filter((rule) => REDUCED_MOTION.test(rule.media ?? ''))
      const stopping = reduced.filter((rule) => stopsMotion(rule.declarations))
      expect(stopping.length, `nothing stops ${name(element)} under prefers-reduced-motion: reduce`).toBeGreaterThan(0)
      // And nothing under that condition sets an animation going again.
      const started = motionIn(reduced.flatMap((rule) => rule.declarations)).names.filter(
        (animationName) => animationName !== 'none',
      )
      expect(started, `${name(element)} is animated under prefers-reduced-motion: reduce`).toEqual([])
    }
  })
})
