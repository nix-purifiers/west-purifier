{
  lib,
  runCommand,
  fetchurl,
  fetchgit,
  writeText,
  python3,
  purifier,
  sdkVersion,
  ...
}:
{
  lock,
  fetchers ? { },
}:
let
  checked = purifier.checkLock lock;
  tree = purifier.tree (
    {
      name = "west-locked-git-sources";
      entries = checked.entries;
      inherit
        runCommand
        fetchurl
        fetchgit
        writeText
        python3
        ;
    }
    // fetchers
  );
  projects = map (entry: {
    name = entry.west.name;
    path = entry.path;
    source = runCommand "west-native-project-${entry.west.name}" { } ''
      mkdir -p "$out"
      cp -pr ${lib.escapeShellArg "${tree}/${entry.path}/."} "$out/"
      chmod -R u+w "$out"
      mkdir -p "$out/.git/refs/heads"
      printf '%s\n' ${lib.escapeShellArg entry.git.rev} > "$out/.git/refs/heads/manifest-rev"
    '';
  }) checked.entries;
  frozen = writeText "west-frozen-manifest.json" (builtins.toJSON checked.data.frozen);
  manifest = writeText "west-environment.json" (
    builtins.toJSON {
      inherit tree projects frozen;
      sdk = sdkVersion;
      inherit (checked.data) manifestPath nativeConfig;
    }
  );
  output = runCommand "west-locked-environment" { passthru = { inherit projects; }; } ''
    mkdir -p "$out"
    ln -s ${manifest} "$out/manifest.json"
  '';
in
assert lib.assertMsg (checked.data.sdk == sdkVersion) "West SDK changed; update the lock";
{
  inherit
    output
    tree
    projects
    frozen
    ;
}
