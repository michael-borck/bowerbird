#!/usr/bin/env node
import { Command } from 'commander';
import { suggestResources } from '@michaelborck/bowerbird-core';

const program = new Command();

program
  .name('bowerbird')
  .description('Finds and verifies supporting resources for your teaching.')
  .version('0.1.0');

program
  .command('suggest')
  .description('List mode: verified, annotated resources for a topic')
  .argument('<topic...>', 'topic to find supporting resources for')
  .option('-n, --max-results <n>', 'maximum number of resources', '10')
  .action(async (topicWords: string[], options: { maxResults: string }) => {
    const result = await suggestResources({
      input: topicWords.join(' '),
      maxResults: Number(options.maxResults),
    });
    process.stdout.write(JSON.stringify(result, null, 2) + '\n');
  });

program.parseAsync().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
