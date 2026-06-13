import { descriptionBlocks } from './description-blocks';

describe('descriptionBlocks', (): void => {
  it('parses headings and bullets', (): void => {
    expect(
      descriptionBlocks(
        '##\nCompany:\n\nQualcomm Canada ULC\n\n## Responsibilities\n\n- Build models\n* Validate **RTL**\n\nApply today.',
      ),
    ).toEqual([
      { kind: 'heading', text: 'Company' },
      { kind: 'paragraph', text: 'Qualcomm Canada ULC' },
      { kind: 'heading', text: 'Responsibilities' },
      { kind: 'list', items: ['Build models', 'Validate RTL'] },
      { kind: 'paragraph', text: 'Apply today.' },
    ]);
  });
});
