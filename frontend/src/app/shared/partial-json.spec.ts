import { parsePartialJson } from './partial-json';

describe('parsePartialJson', (): void => {
  it('reads complete json', (): void => {
    expect(parsePartialJson('{"a":[1,2]}')).toEqual({ value: { a: [1, 2] }, complete: true });
    expect(parsePartialJson('```json\n{"a":1}\n```')).toEqual({ value: { a: 1 }, complete: true });
  });

  it.each([
    ['{"text":"Built a par', { text: 'Built a par' }],
    ['{"items":["one","tw', { items: ['one', 'tw'] }],
    ['{"a":1,"b"', { a: 1 }],
    ['{"quote":"say \\"hi', { quote: 'say "hi' }],
  ])('closes a cut-off document so its fields can be shown: %s', (text, value): void => {
    expect(parsePartialJson(text)).toEqual({ value, complete: false });
  });

  it('gives up on text that is not JSON', (): void => {
    expect(parsePartialJson('')).toBeNull();
    expect(parsePartialJson('Thinking about it')).toBeNull();
    expect(parsePartialJson('[Earlier output omitted from console]\n"a":1}')).toBeNull();
  });
});
