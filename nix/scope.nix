{
  pkgs,
  nixpkgsSrc,
  purifierSrc,
}:
pkgs.lib.makeScope pkgs.newScope (scope: {
  original = pkgs.python3.withPackages (ps: [ ps.west ]);
  core = pkgs.python3.pkgs.west.overrideAttrs (old: {
    postPatch = (old.postPatch or "") + ''
      ${pkgs.python3}/bin/python3 ${../native/patch-native.py}
    '';
  });
  tool = pkgs.python3.withPackages (ps: [
    scope.core
    ps.pip
  ]);
  purifier = import (purifierSrc + "/nix/lib") { inherit (pkgs) lib; };
  sdkVersion = builtins.hashString "sha256" (
    builtins.toJSON {
      nixpkgs = toString nixpkgsSrc;
      core = toString pkgs.python3.pkgs.west.src;
      patch = builtins.hashFile "sha256" ../native/patch-native.py;
    }
  );
  cli = scope.callPackage ./cli.nix { inherit nixpkgsSrc purifierSrc; };
  buildWestProject = scope.callPackage ./build-project.nix { };
})
