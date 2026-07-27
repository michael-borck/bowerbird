#!/usr/bin/env node
import path from 'node:path';
import { Command } from 'commander';
import {
  suggestResources,
  configFromEnv,
  toMarkdown,
  extract,
} from '@michaelborck/bowerbird-core';

const program = new Command();

program
  .name('bowerbird')
  .description('Finds and verifies supporting resources for your teaching.')
  .version('0.1.1');

program
  .command('suggest')
  .description('List mode: verified, annotated resources for a topic or document')
  .argument('[topic...]', 'topic to find supporting resources for')
  .option('-f, --file <path>', 'read the topic from a document (PDF, DOCX, TXT, MD)')
  .option('-n, --max-results <n>', 'maximum number of resources', '10')
  .option('--json', 'output JSON instead of markdown')
  .action(
    async (
      topicWords: string[],
      options: { file?: string; maxResults: string; json?: boolean },
    ) => {
      let input = topicWords.join(' ');
      let label = input;
      if (options.file) {
        const doc = await extract(options.file);
        input = doc.text;
        label = label || path.basename(options.file);
      }
      if (!input.trim()) {
        program.error('Provide a topic or --file <path>.');
      }
      const result = await suggestResources(
        { input, maxResults: Number(options.maxResults) },
        configFromEnv(),
      );
      const out = options.json
        ? JSON.stringify(result, null, 2)
        : toMarkdown(label, result);
      process.stdout.write(out + '\n');
    },
  );

program.parseAsync().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
