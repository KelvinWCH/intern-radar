import type { Observable } from 'rxjs';
import {
  EMPTY,
  defer,
  distinctUntilChanged,
  filter,
  fromEvent,
  map,
  startWith,
  switchMap,
  take,
  timer,
} from 'rxjs';

export function visiblePoll(page: Document, delay: number, period: number): Observable<number> {
  return defer(() =>
    fromEvent(page, 'visibilitychange').pipe(
      startWith(null),
      map((): boolean => !page.hidden),
      distinctUntilChanged(),
      switchMap((visible) => (visible ? timer(delay, period) : EMPTY)),
    ),
  );
}

export function visibleDelay(page: Document, delay: number): Observable<unknown> {
  return timer(delay).pipe(
    switchMap(() => fromEvent(page, 'visibilitychange').pipe(startWith(null))),
    filter((): boolean => !page.hidden),
    take(1),
  );
}
