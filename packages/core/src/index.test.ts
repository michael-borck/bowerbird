import { test } from 'node:test';
import assert from 'node:assert/strict';
import { suggestResources } from './index.ts';

test('suggestResources is a stub until v1 lands', async () => {
  await assert.rejects(
    suggestResources({ input: 'supply chain resilience' }),
    /Not implemented/,
  );
});
