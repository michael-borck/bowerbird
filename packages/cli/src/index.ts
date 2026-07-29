#!/usr/bin/env node
import path from 'node:path';
import { readFile } from 'node:fs/promises';
import { Command } from 'commander';
import {
  suggestResources,
  suggestBatch,
  toBatchMarkdown,
  recheckResources,
  toRecheckMarkdown,
  configFromEnv,
  toMarkdown,
  toCitations,
  toLmsHtml,
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
  .option(
    '-o, --format <format>',
    'output format: markdown, json, html (LMS-ready), apa, harvard',
    'markdown',
  )
  .option('--json', 'shorthand for --format json')
  .option('-c, --counterpoint', 'also surface material disagreeing with the framing')
  .action(
    async (
      topicWords: string[],
      options: {
        file?: string;
        maxResults: string;
        format: string;
        json?: boolean;
        counterpoint?: boolean;
      },
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
        {
          input,
          maxResults: Number(options.maxResults),
          counterpoint: Boolean(options.counterpoint),
        },
        configFromEnv(),
      );
      const format = options.json ? 'json' : options.format;
      let out: string;
      switch (format) {
        case 'json':
          out = JSON.stringify(result, null, 2);
          break;
        case 'html':
          out = toLmsHtml(label, result);
          break;
        case 'apa':
        case 'harvard':
          out = toCitations(result, format);
          break;
        default:
          out = toMarkdown(label, result);
      }
      process.stdout.write(out + '\n');
    },
  );

program
  .command('batch')
  .description('Batch mode: verified resources for many topics at once (one per line)')
  .argument('<file>', 'text file with one topic per line')
  .option('-n, --max-results <n>', 'maximum resources per topic', '8')
  .option('-c, --counterpoint', 'also surface disagreeing material per topic')
  .option('--json', 'output JSON instead of markdown')
  .action(
    async (
      file: string,
      options: { maxResults: string; counterpoint?: boolean; json?: boolean },
    ) => {
      const topics = (await readFile(file, 'utf8'))
        .split('\n')
        .map((l) => l.trim())
        .filter((l) => l && !l.startsWith('#'));
      if (!topics.length) program.error('No topics found in file.');
      const entries = await suggestBatch(topics, configFromEnv(), {
        maxResults: Number(options.maxResults),
        counterpoint: Boolean(options.counterpoint),
      });
      process.stdout.write(
        (options.json ? JSON.stringify({ entries }, null, 2) : toBatchMarkdown(entries)) +
          '\n',
      );
    },
  );

program
  .command('recheck')
  .description('Link-rot re-run: re-verify a previously saved JSON result list')
  .argument('<file>', 'JSON file from a previous `suggest --json` run')
  .option('--json', 'output JSON instead of markdown')
  .action(async (file: string, options: { json?: boolean }) => {
    const saved = JSON.parse(await readFile(file, 'utf8'));
    const resources = saved.resources ?? saved.entries?.flatMap((e: { result: { resources: unknown[] } }) => e.result.resources);
    if (!Array.isArray(resources) || !resources.length) {
      program.error('No resources found in file — expected suggest/batch JSON output.');
    }
    const entries = await recheckResources(resources);
    process.stdout.write(
      (options.json ? JSON.stringify({ entries }, null, 2) : toRecheckMarkdown(entries)) +
        '\n',
    );
  });

program.parseAsync().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
