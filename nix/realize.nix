{
  root,
  lockFile,
  sdk,
}:
let
  nixpkgsSrc = /. + "@nixpkgs@";
  pkgs = import nixpkgsSrc { };
  scope = import ./scope.nix {
    inherit pkgs nixpkgsSrc;
    purifierSrc = /. + "@purifier@";
  };
  lock = import ../lib-overlays/default/read-lock.nix { inherit (pkgs) lib; } {
    src = /. + root;
    lockFile = /. + lockFile;
  };
  environment = scope.callPackage ../pkgs/build-west-project/environment.nix { } { inherit lock; };
in
pkgs.writeText "west-environment-profile.json" (
  builtins.toJSON {
    output = environment.output;
    sdk = builtins.storePath sdk;
  }
)
