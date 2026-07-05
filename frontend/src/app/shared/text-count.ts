export function countCharacters(text: string): number {
  let count = 0;
  for (const character of text) {
    count += character ? 1 : 0;
  }
  return count;
}
