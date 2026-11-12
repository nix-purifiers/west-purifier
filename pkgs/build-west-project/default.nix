{
  lib,
  runCommand,
  writeText,
  python3,
  fetchurl,
  fetchgit,
  purifier,
  tool,
  sdkVersion,
  gnutar,
  gzip,
  cmake,
  gnumake,
  gcc,
  ...
}@scope:
{
  src,
  lockFile ? src + "/west-purifier.lock.json",
  command ? [ "build" ],
  nativeBuildInputs ? [
    cmake
    gnumake
    gcc
  ],
  fetchers ? { },
  doCheck ? false,
  checkCommand ? "",
  version ? "v0.1.0",
  installCommand ? ''cmake --install build --prefix "$out"'',
}:
let
  lock = purifier.checkLock (import ../../lib-overlays/default/read-lock.nix { inherit lib; } { inherit src lockFile; });
  prepared = import ./environment.nix scope { inherit lock fetchers; };
  source = lib.cleanSourceWith {
    inherit src;
    filter =
      path: type:
      !(builtins.elem (baseNameOf path) [
        ".git"
        "build"
        "result"
        "__pycache__"
        ".venv"
      ]);
  };
  project = runCommand "west-project" { nativeBuildInputs = [ tool ] ++ nativeBuildInputs; } ''
    cp -pr ${source} source
    chmod -R u+w source
    cd source
    mkdir -p "$out"
    ${python3}/bin/python3 ${../../west_purifier/layout.py} "$TMPDIR/workspace" "$PWD" ${prepared.output}/manifest.json \
      ${tool}/bin/west ${lib.escapeShellArgs command} > "$TMPDIR/build.log" 2>&1 || { cat "$TMPDIR/build.log"; exit 1; }
    ${installCommand}
    ${lib.optionalString doCheck checkCommand}
    cp -pr ${source} "$out/source"
  '';
  release =
    runCommand "west-native-release"
      {
        nativeBuildInputs = [
          gnutar
          gzip
        ];
      }
      ''
        test -d ${project}
        mkdir -p "$out"
        tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -czf "$out/west-project.tar.gz" -C ${source} .
      '';
in
{
  packages = {
    default = project;
    inherit project;
    environment = prepared.output;
  };
  tests = project;
  inherit release;
  fetches = lock.entries;
}
