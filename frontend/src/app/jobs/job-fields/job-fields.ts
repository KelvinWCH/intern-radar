import { Component, input } from '@angular/core';
import { ControlContainer, FormsModule, NgForm } from '@angular/forms';
import { TextCount } from '../../shared/text-count/text-count';
import {
  storedDescriptionLimit,
  tailoringDescriptionLimit,
} from '../constants/description.constants';
import {
  educationListFields,
  jobLinkFields,
  jobTextFields,
  qualificationBooleanFields,
  qualificationNumberFields,
  requirementListFields,
} from '../constants/job-fields.constants';
import type { JobDraft } from '../models/job-details.models';

@Component({
  selector: 'app-job-fields',
  imports: [FormsModule, TextCount],
  viewProviders: [{ provide: ControlContainer, useExisting: NgForm }],
  templateUrl: './job-fields.html',
  styleUrl: './job-fields.scss',
})
export class JobFields {
  readonly draft = input.required<JobDraft>();
  readonly editing = input(false);
  protected readonly storedDescriptionLimit = storedDescriptionLimit;
  protected readonly tailoringDescriptionLimit = tailoringDescriptionLimit;
  protected readonly requirementListFields = requirementListFields;
  protected readonly educationListFields = educationListFields;
  protected readonly jobLinkFields = jobLinkFields;
  protected readonly jobTextFields = jobTextFields;
  protected readonly qualificationNumberFields = qualificationNumberFields;
  protected readonly qualificationBooleanFields = qualificationBooleanFields;
}
