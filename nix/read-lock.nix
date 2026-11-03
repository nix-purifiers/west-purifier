{ lib }:
{
  src,
  lockFile ? src + "/west-purifier.lock.json",
}:
let
  raw = if builtins.pathExists lockFile then builtins.fromJSON (builtins.readFile lockFile) else { };
  data = if builtins.isAttrs raw then raw else { };
  entries = data.entries or [ ];
  relative =
    s:
    builtins.isString s
    && s != ""
    && s != "."
    && !(lib.hasPrefix "/" s)
    && !(builtins.elem ".." (lib.splitString "/" s))
    && builtins.match ".*[\n\r].*" s == null;
  shape =
    (data.version or null) == 1
    && (data.purifier or null) == "west"
    && builtins.isString (data.sdk or null)
    && relative (data.manifestPath or null)
    && relative (data.manifestFile or null)
    && builtins.isAttrs (data.nativeConfig or null)
    && builtins.all builtins.isString (builtins.attrValues data.nativeConfig)
    && builtins.isAttrs (data.inputs or null)
    && builtins.isAttrs (data.directories or null)
    && builtins.isAttrs (data.frozen or null)
    && builtins.isAttrs (data.frozen.manifest or null)
    && builtins.isList (data.frozen.manifest.projects or [ ])
    && builtins.isList entries
    && builtins.length entries == builtins.length (data.frozen.manifest.projects or [ ])
    && builtins.all (
      e:
      builtins.isAttrs e
      && relative (e.path or null)
      && builtins.isAttrs (e.git or null)
      && builtins.isAttrs (e.west or null)
      && builtins.isString (e.west.name or null)
      && builtins.isString (e.git.url or null)
      && lib.hasPrefix "https://" e.git.url
      && builtins.isString (e.git.rev or null)
      && builtins.match "[0-9a-f]{40}" e.git.rev != null
      && (e.git.submodules or null) == false
      && (e.git.leaveDotGit or null) == true
      && builtins.isAttrs (e.git.commitObject or null)
      && builtins.isString (e.git.commitObject.object or null)
      && builtins.isList (e.git.commitObject.gitlinks or null)
      && builtins.isString (e.hash or null)
      && builtins.match "sha256-[A-Za-z0-9+/]{43}=" e.hash != null
    ) entries;
  valid =
    shape
    && builtins.hasAttr data.manifestFile data.inputs
    && builtins.length (lib.unique (map (e: e.path) entries)) == builtins.length entries
    && builtins.all (
      i:
      let
        e = builtins.elemAt entries i;
        p = builtins.elemAt data.frozen.manifest.projects i;
      in
      e.path == (p.path or p.name)
      && e.west.name == p.name
      && e.git.url == p.url
      && e.git.rev == p.revision
      && !(lib.hasPrefix "${data.manifestPath}/" e.path)
      && e.path != data.manifestPath
      && !(lib.hasPrefix "${e.path}/" data.manifestPath)
    ) (lib.range 0 (builtins.length entries - 1))
    && builtins.all (
      name:
      relative name
      && builtins.pathExists (src + "/${name}")
      && builtins.hashFile "sha256" (src + "/${name}") == (data.inputs.${name}.sha256 or null)
    ) (builtins.attrNames data.inputs)
    && builtins.all (
      name:
      (name == "." || relative name)
      && builtins.pathExists (src + "/${name}")
      &&
        builtins.filter (n: lib.hasSuffix ".yml" n || lib.hasSuffix ".yaml" n) (
          builtins.attrNames (builtins.readDir (src + "/${name}"))
        ) == data.directories.${name}
    ) (builtins.attrNames data.directories);
in
{
  purifier = "west";
  inherit data entries;
  problems = lib.optional (
    !valid
  ) "West lock is missing, malformed, or stale; run west-purifier lock --update";
  outputs = {
    packages = [
      "default"
      "environment"
      "project"
    ];
    tests = [ "default" ];
    release = [ "default" ];
  };
}
