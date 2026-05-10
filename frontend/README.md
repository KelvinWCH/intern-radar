# frontend

Angular 21 app (standalone components, signals, PrimeNG).

```sh
npm ci
npm start          # http://localhost:4200
npm run check      # lint, typecheck, prettier, production build, tests
npm run lint:fix   # fix lint errors and prettier formatting in src
```

ESLint runs prettier as a rule (`eslint-plugin-prettier/recommended`), so formatting problems in
`.ts` and `.html` files show up next to the lint errors. `npm run format` formats everything else.

`npm start` passes `/api` to the backend on `http://127.0.0.1:8000` (see `proxy.conf.json`). In
Docker, nginx does the same thing.

## Layout

| Folder                    | Pages                                                           |
| ------------------------- | --------------------------------------------------------------- |
| `src/app/workspace/`      | home page: daily report, scrape panel and scrape progress       |
| `src/app/jobs/`           | job calendar and list, job page, add a job                      |
| `src/app/tailor/`         | tailoring flow, documents, resume editor, application questions |
| `src/app/resume-manager/` | your profile                                                    |
| `src/app/scrapes/`        | scrape controls and history                                     |
| `src/app/activity/`       | activity page                                                   |
| `src/app/settings/`       | default models and sign out                                     |
| `src/app/shared/`         | shared components and api validation                            |

Every response from the api is validated at runtime before it reaches a component (see the
`parse*` functions next to each model).
