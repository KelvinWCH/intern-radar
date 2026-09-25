// events read "Research: found 4 sources"; older saved events used a middle dot instead of the colon
const separator = /: | · /;

export function eventSource(message: string): string {
  const match = separator.exec(message);
  return match ? message.slice(0, match.index) : '';
}

export function eventDetail(message: string): string {
  const match = separator.exec(message);
  return match ? message.slice(match.index + match[0].length) : message;
}
