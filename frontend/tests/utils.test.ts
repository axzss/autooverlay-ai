import { describe, it, expect } from 'vitest'
import { cn } from '../app/lib/utils'

describe('cn', () => {
  it('joins plain class names', () => {
    expect(cn('a', 'b')).toBe('a b')
  })

  it('drops falsy values', () => {
    expect(cn('a', false, undefined, null, '', 'b')).toBe('a b')
  })

  it('supports conditional objects and arrays', () => {
    expect(cn({ a: true, b: false }, ['c', 'd'])).toBe('a c d')
  })

  it('lets the later tailwind class win on a conflict', () => {
    expect(cn('p-2', 'p-4')).toBe('p-4')
    expect(cn('text-red-500', 'text-blue-500')).toBe('text-blue-500')
  })

  it('keeps non-conflicting tailwind classes', () => {
    expect(cn('px-2', 'py-4')).toBe('px-2 py-4')
  })

  it('returns an empty string for no input', () => {
    expect(cn()).toBe('')
  })
})
