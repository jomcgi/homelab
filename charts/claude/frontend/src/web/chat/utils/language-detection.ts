/**
 * Utility for detecting programming languages from file paths/extensions
 */

// Map of file extensions to language identifiers used by syntax highlighters
const extensionToLanguage: Record<string, string> = {
  // JavaScript/TypeScript
  '.js': 'javascript',
  '.jsx': 'jsx',
  '.ts': 'typescript',
  '.tsx': 'tsx',
  '.mjs': 'javascript',
  '.cjs': 'javascript',
  
  // Python
  '.py': 'python',
  '.pyw': 'python',
  '.pyi': 'python',
  
  // Web
  '.html': 'html',
  '.htm': 'html',
  '.xml': 'xml',
  '.css': 'css',
  '.scss': 'scss',
  '.sass': 'sass',
  '.less': 'less',
  
  // Data formats
  '.json': 'json',
  '.yaml': 'yaml',
  '.yml': 'yaml',
  '.toml': 'toml',
  '.ini': 'ini',
  
  // Shell/Bash
  '.sh': 'bash',
  '.bash': 'bash',
  '.zsh': 'bash',
  '.fish': 'bash',
  
  // C/C++
  '.c': 'c',
  '.h': 'c',
  '.cpp': 'cpp',
  '.cc': 'cpp',
  '.cxx': 'cpp',
  '.hpp': 'cpp',
  '.hxx': 'cpp',
  
  // Java/Kotlin
  '.java': 'java',
  '.kt': 'kotlin',
  '.kts': 'kotlin',
  
  // Go
  '.go': 'go',
  
  // Rust
  '.rs': 'rust',
  
  // Ruby
  '.rb': 'ruby',
  '.rake': 'ruby',
  
  // PHP
  '.php': 'php',
  '.phtml': 'php',
  
  // Swift
  '.swift': 'swift',
  
  // Objective-C
  '.mm': 'objectivec',
  
  // C#
  '.cs': 'csharp',
  
  // SQL
  '.sql': 'sql',
  
  // Markdown
  '.md': 'markdown',
  '.markdown': 'markdown',
  
  // Docker
  '.dockerfile': 'dockerfile',
  
  // Make
  '.makefile': 'makefile',
  '.mk': 'makefile',
  
  // Vim
  '.vim': 'vim',
  '.vimrc': 'vim',
  
  // Lua
  '.lua': 'lua',
  
  // R
  '.r': 'r',
  '.R': 'r',
  
  // Scala
  '.scala': 'scala',
  '.sc': 'scala',
  
  // Clojure
  '.clj': 'clojure',
  '.cljs': 'clojure',
  '.cljc': 'clojure',
  
  // Haskell
  '.hs': 'haskell',
  '.lhs': 'haskell',
  
  // Elixir
  '.ex': 'elixir',
  '.exs': 'elixir',
  
  // Erlang
  '.erl': 'erlang',
  '.hrl': 'erlang',
  
  // OCaml
  '.ml': 'ocaml',
  '.mli': 'ocaml',
  
  // F#
  '.fs': 'fsharp',
  '.fsi': 'fsharp',
  '.fsx': 'fsharp',
  
  // Dart
  '.dart': 'dart',
  
  // Perl
  '.pl': 'perl',
  '.pm': 'perl',
  
  // Groovy
  '.groovy': 'groovy',
  '.gradle': 'groovy',
  
  // LaTeX
  '.tex': 'latex',
  '.latex': 'latex',
  
  // MATLAB
  '.m': 'matlab',
  '.mat': 'matlab',
  
  // Powershell
  '.ps1': 'powershell',
  '.psm1': 'powershell',
  '.psd1': 'powershell',
  
  // Assembly
  '.asm': 'asm',
  '.s': 'asm',
  
  // GLSL
  '.glsl': 'glsl',
  '.vert': 'glsl',
  '.frag': 'glsl',
  
  // GraphQL
  '.graphql': 'graphql',
  '.gql': 'graphql',
  
  // Prisma
  '.prisma': 'prisma',
  
  // Solidity
  '.sol': 'solidity',
  
  // Vue
  '.vue': 'vue',
  
  // Svelte
  '.svelte': 'svelte',
  
  // Nix
  '.nix': 'nix',
  
  // Julia
  '.jl': 'julia',
  
  // Zig
  '.zig': 'zig',
  
  // V
  '.vsh': 'v',
  
  // Crystal
  '.cr': 'crystal',
  
  // Nim
  '.nim': 'nim',
  '.nims': 'nim',
  
  // D
  '.d': 'd',
  '.di': 'd',
  
  // Pascal
  '.pas': 'pascal',
  '.pp': 'pascal',
  '.inc': 'pascal',
  
  // Fortran
  '.f': 'fortran',
  '.for': 'fortran',
  '.f90': 'fortran',
  '.f95': 'fortran',
  
  // COBOL
  '.cob': 'cobol',
  '.cbl': 'cobol',
  
  // Ada
  '.ada': 'ada',
  '.adb': 'ada',
  '.ads': 'ada',
  
  // Prolog
  '.pro': 'prolog',
  '.P': 'prolog',
  
  // Scheme
  '.scm': 'scheme',
  '.ss': 'scheme',
  
  // Racket
  '.rkt': 'racket',
  
  // Common Lisp
  '.lisp': 'lisp',
  '.lsp': 'lisp',
  '.cl': 'lisp',
  
  // Tcl
  '.tcl': 'tcl',
  
  // AWK
  '.awk': 'awk',
  
  // SAS
  '.sas': 'sas',
  
  // VHDL
  '.vhd': 'vhdl',
  '.vhdl': 'vhdl',
  
  // Verilog
  '.v': 'verilog',
  '.vh': 'verilog',
  '.sv': 'verilog',
  
  // WebAssembly
  '.wat': 'wasm',
  '.wast': 'wasm',
};

// Map of filenames to languages (for files without extensions)
const filenameToLanguage: Record<string, string> = {
  'Dockerfile': 'dockerfile',
  'Makefile': 'makefile',
  'Rakefile': 'ruby',
  'Gemfile': 'ruby',
  '.gitignore': 'gitignore',
  '.gitattributes': 'gitignore',
  '.npmignore': 'gitignore',
  '.dockerignore': 'gitignore',
  '.env': 'bash',
  '.bashrc': 'bash',
  '.zshrc': 'bash',
  '.bash_profile': 'bash',
  '.profile': 'bash',
  'nginx.conf': 'nginx',
  'httpd.conf': 'apache',
  '.htaccess': 'apache',
};

/**
 * Detect the programming language from a file path
 * @param filePath The file path to analyze
 * @returns The detected language identifier, or 'text' if not detected
 */
export function detectLanguageFromPath(filePath: string): string {
  if (!filePath) {
    return 'text';
  }

  // Extract filename from path
  const pathParts = filePath.split('/');
  const filename = pathParts[pathParts.length - 1];
  
  // Check if it's a known filename
  if (filenameToLanguage[filename]) {
    return filenameToLanguage[filename];
  }
  
  // Extract extension
  const lastDotIndex = filename.lastIndexOf('.');
  if (lastDotIndex === -1 || lastDotIndex === 0) {
    // No extension or hidden file without extension
    return 'text';
  }
  
  const extension = filename.slice(lastDotIndex).toLowerCase();
  
  // Look up language by extension
  return extensionToLanguage[extension] || 'text';
}

/**
 * Check if a file path represents a code file that should have syntax highlighting
 * @param filePath The file path to check
 * @returns true if the file should have syntax highlighting
 */
export function isCodeFile(filePath: string): boolean {
  const language = detectLanguageFromPath(filePath);
  return language !== 'text';
}

/**
 * Get a human-readable language name from a language identifier
 * @param language The language identifier
 * @returns A human-readable language name
 */
export function getLanguageDisplayName(language: string): string {
  const displayNames: Record<string, string> = {
    javascript: 'JavaScript',
    typescript: 'TypeScript',
    jsx: 'JSX',
    tsx: 'TSX',
    python: 'Python',
    java: 'Java',
    csharp: 'C#',
    cpp: 'C++',
    c: 'C',
    go: 'Go',
    rust: 'Rust',
    php: 'PHP',
    ruby: 'Ruby',
    swift: 'Swift',
    kotlin: 'Kotlin',
    scala: 'Scala',
    r: 'R',
    matlab: 'MATLAB',
    sql: 'SQL',
    bash: 'Bash',
    powershell: 'PowerShell',
    dockerfile: 'Dockerfile',
    makefile: 'Makefile',
    yaml: 'YAML',
    json: 'JSON',
    xml: 'XML',
    html: 'HTML',
    css: 'CSS',
    scss: 'SCSS',
    sass: 'Sass',
    less: 'Less',
    markdown: 'Markdown',
    latex: 'LaTeX',
    vim: 'Vim Script',
    lua: 'Lua',
    perl: 'Perl',
    objectivec: 'Objective-C',
    fsharp: 'F#',
    ocaml: 'OCaml',
    haskell: 'Haskell',
    elixir: 'Elixir',
    erlang: 'Erlang',
    clojure: 'Clojure',
    lisp: 'Lisp',
    scheme: 'Scheme',
    racket: 'Racket',
    prolog: 'Prolog',
    fortran: 'Fortran',
    cobol: 'COBOL',
    ada: 'Ada',
    pascal: 'Pascal',
    d: 'D',
    nim: 'Nim',
    crystal: 'Crystal',
    v: 'V',
    zig: 'Zig',
    julia: 'Julia',
    dart: 'Dart',
    groovy: 'Groovy',
    solidity: 'Solidity',
    graphql: 'GraphQL',
    prisma: 'Prisma',
    glsl: 'GLSL',
    wasm: 'WebAssembly',
    vhdl: 'VHDL',
    verilog: 'Verilog',
    asm: 'Assembly',
    nginx: 'Nginx',
    apache: 'Apache',
    gitignore: 'Git Ignore',
    text: 'Plain Text',
  };
  
  return displayNames[language] || language.charAt(0).toUpperCase() + language.slice(1);
}