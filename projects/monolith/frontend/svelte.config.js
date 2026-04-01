import adapter from "@sveltejs/adapter-node";
import { mdsvex } from "mdsvex";

const config = {
  extensions: [".svelte", ".svx"],
  preprocess: [mdsvex()],
  kit: {
    adapter: adapter({
      out: "build",
    }),
  },
};

export default config;
