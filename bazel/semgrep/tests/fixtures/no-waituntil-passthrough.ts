// Tests for no-waituntil-passthrough rule.

// ruleid: no-waituntil-passthrough
const badConfig = {
  waitUntil: (task) => task,
};

// ok: no-waituntil-passthrough
let captured: Promise<unknown>;
const goodClosureConfig = {
  waitUntil: (task) => {
    captured = task;
  },
};

// ok: no-waituntil-passthrough
const tasks: Promise<unknown>[] = [];
const goodPushConfig = {
  waitUntil: (task) => tasks.push(task),
};
