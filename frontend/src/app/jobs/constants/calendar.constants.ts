import type { CalendarDateMode, CalendarDayCount } from '../models/job-calendar.models';

export const calendarDayCounts: readonly CalendarDayCount[] = [1, 3, 5, 7];

export const calendarDateModes: readonly CalendarDateMode[] = [
  {
    value: 'scraped',
    label: 'Scraped date',
    icon: 'pi-download',
    description: 'Grouped by when jobs were first found.',
  },
  {
    value: 'posted',
    label: 'Posted date',
    icon: 'pi-calendar',
    description: 'Grouped by employer posting date, or the scraped date when it is unknown.',
  },
];
