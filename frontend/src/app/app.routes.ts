import type { Routes } from '@angular/router';
import { confirmLeavingResumeEditor } from './tailor/resume-editor/leave-guard';

export const routes: Routes = [
  {
    path: '',
    title: 'Workspace - Intern Radar',
    loadComponent: () => import('./workspace/workspace').then((module) => module.Workspace),
  },
  {
    path: 'jobs/new',
    title: 'Add a job - Intern Radar',
    loadComponent: () => import('./jobs/add-job/add-job').then((module) => module.AddJob),
  },
  {
    path: 'tailor',
    title: 'Tailor your application - Intern Radar',
    loadComponent: () => import('./tailor/tailor').then((module) => module.Tailor),
  },
  {
    path: 'jobs',
    title: 'Jobs - Intern Radar',
    loadComponent: () =>
      import('./jobs/job-library/job-library').then((module) => module.JobLibrary),
  },
  {
    path: 'applications',
    title: 'Applications - Intern Radar',
    data: { tracker: true },
    loadComponent: () =>
      import('./jobs/job-library/job-library').then((module) => module.JobLibrary),
  },
  {
    path: 'jobs/:id',
    title: 'Job details - Intern Radar',
    loadComponent: () => import('./jobs/job-detail/job-detail').then((module) => module.JobDetail),
  },
  {
    path: 'activity',
    title: 'Activity - Intern Radar',
    loadComponent: () => import('./activity/activity').then((module) => module.Activity),
  },
  {
    path: 'profile',
    title: 'Your profile - Intern Radar',
    loadComponent: () =>
      import('./resume-manager/resume-manager').then((module) => module.ResumeManager),
  },
  {
    path: 'documents',
    title: 'Documents - Intern Radar',
    loadComponent: () =>
      import('./tailor/document-history/document-history').then((module) => module.DocumentHistory),
  },
  {
    path: 'documents/:id',
    title: 'Document details - Intern Radar',
    loadComponent: () =>
      import('./tailor/document-detail/document-detail').then((module) => module.DocumentDetail),
  },
  {
    path: 'documents/:id/resume',
    title: 'Edit resume - Intern Radar',
    canDeactivate: [confirmLeavingResumeEditor],
    loadComponent: () =>
      import('./tailor/resume-editor/resume-editor').then((module) => module.ResumeEditor),
  },
  {
    path: 'scrapes',
    title: 'Scrapes - Intern Radar',
    loadComponent: () =>
      import('./scrapes/scrape-history/scrape-history').then((module) => module.ScrapeHistory),
  },
  {
    path: 'settings',
    title: 'Settings - Intern Radar',
    loadComponent: () => import('./settings/settings').then((module) => module.Settings),
  },
  {
    path: 'sign-in',
    title: 'Sign in - Intern Radar',
    loadComponent: () => import('./sign-in/sign-in').then((module) => module.SignIn),
  },
  { path: 'resume', redirectTo: 'profile', pathMatch: 'full' },
  { path: '**', redirectTo: '' },
];
