import adapter from "@sveltejs/adapter-static";
import { mdsvex } from "mdsvex";

const config = {
  extensions: [".svelte", ".svx"],
  preprocess: [mdsvex()],
  kit: {
    adapter: adapter({
      fallback: "index.html",
    }),
    paths: {
      base: "",
    },
  },
};

export default config;
