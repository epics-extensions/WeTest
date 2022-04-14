{
  description = "A very basic flake";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-21.11";

  outputs = { self, nixpkgs }: let
      pkgs = nixpkgs.legacyPackages.x86_64-linux;
    in {

    packages.x86_64-linux.default = pkgs.poetry2nix.mkPoetryApplication {
      projectDir = ./.;

      propagatedBuildInputs = with pkgs.python3Packages; [ tkinter ];

      overrides = pkgs.poetry2nix.overrides.withDefaults (final: prev: {
        reportlab = prev.reportlab.overridePythonAttrs (old: {
          buildInputs = with pkgs; [ (freetype.overrideAttrs (_: { dontDisableStatic = true; })) ];
        });
      });
    };

    devShells.x86_64-linux.default = pkgs.mkShell {
      nativeBuildInputs = with pkgs; [ poetry python3Full ];
    };

  };
}
